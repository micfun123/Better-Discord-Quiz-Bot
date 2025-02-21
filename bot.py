import discord
import json
import os
from discord.ext import commands
from discord.ui import View, Button
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# Load quiz data from JSON
def load_quiz_data():
    if os.path.exists("quiz_data.json"):
        with open("quiz_data.json", "r") as file:
            return json.load(file)
    return {}

def save_quiz_data():
    with open("quiz_data.json", "w") as file:
        json.dump(quiz_data, file, indent=4)

quiz_data = load_quiz_data()
quizzes = {}

class Quiz:
    def __init__(self, quiz_name, quiz_starter_id, allow_multiple_answers=False):
        self.quiz_name = quiz_name
        self.quiz_starter_id = quiz_starter_id
        self.current_question_index = -1
        self.votes = {}
        self.allow_multiple_answers = allow_multiple_answers
    
    def get_current_question(self):
        if self.current_question_index < len(quiz_data[self.quiz_name]["questions"]):
            return quiz_data[self.quiz_name]["questions"][self.current_question_index]
        return None

class QuizView(View):
    def __init__(self, options, quiz_instance):
        super().__init__()
        self.options = options
        self.quiz_instance = quiz_instance
        for option in options:
            self.add_item(QuizButton(label=option, parent_view=self))

class QuizButton(Button):
    def __init__(self, label, parent_view):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        quiz_instance = self.parent_view.quiz_instance

        if quiz_instance.allow_multiple_answers:
            if user_id not in quiz_instance.votes:
                quiz_instance.votes[user_id] = set()
            
            if self.label in quiz_instance.votes[user_id]:
                quiz_instance.votes[user_id].remove(self.label)
                quiz_instance.votes[self.label] = quiz_instance.votes.get(self.label, 0) - 1
            else:
                quiz_instance.votes[user_id].add(self.label)
                quiz_instance.votes[self.label] = quiz_instance.votes.get(self.label, 0) + 1
        else:
            if user_id in quiz_instance.votes:
                prev_vote = quiz_instance.votes[user_id]
                if isinstance(prev_vote, str):
                    quiz_instance.votes[prev_vote] -= 1
            
            quiz_instance.votes[user_id] = self.label
            quiz_instance.votes[self.label] = quiz_instance.votes.get(self.label, 0) + 1
        
        await interaction.response.send_message(f"You voted for {self.label}", ephemeral=True)

@bot.command()
async def start_quiz(ctx, quiz_name: str, allow_multiple_answers: bool = False):
    if quiz_name not in quiz_data:
        await ctx.send("Quiz not found.")
        return
    
    channel_id = ctx.channel.id
    if channel_id in quizzes:
        await ctx.send("A quiz is already running in this channel.")
        return
    
    quizzes[channel_id] = Quiz(quiz_name, ctx.author.id, allow_multiple_answers)
    await send_question(ctx, quizzes[channel_id])

async def send_question(ctx, quiz_instance):
    quiz_instance.current_question_index += 1
    if quiz_instance.current_question_index >= len(quiz_data[quiz_instance.quiz_name]["questions"]):
        await ctx.send("The quiz has ended!")
        del quizzes[ctx.channel.id]
        return
    
    question_data = quiz_instance.get_current_question()
    question = question_data["question"].replace("\n", "\n").replace("\r", " ").replace("\t", " ")
    options = question_data["options"]
    
    if len(options) < 2:
        await ctx.send("You need at least two options.")
        return
    
    quiz_instance.votes = {option: 0 for option in options}  # Reset votes with all options
    view = QuizView(options, quiz_instance)
    await ctx.send(f"**Question {quiz_instance.current_question_index + 1}: {question}**", view=view)

@bot.command()
async def next_question(ctx):
    channel_id = ctx.channel.id
    if channel_id not in quizzes:
        await ctx.send("No quiz is currently running in this channel. Use `+start_quiz <quiz_name>` to start a quiz.")
        return
    
    quiz_instance = quizzes[channel_id]
    
    # Ensure only the quiz starter can move forward
    if ctx.author.id != quiz_instance.quiz_starter_id:
        await ctx.send("Only the quiz starter can move to the next question.")
        return
    
    # Only display results if at least one question has been asked
    if quiz_instance.current_question_index >= 0:
        total_votes = sum(v for v in quiz_instance.votes.values() if isinstance(v, int))  # Sum only integers
        result_table = "Results\nOption       | Count | %\n"
        result_table += "-" * 30 + "\n"
        
        for option in quiz_instance.votes:
            if isinstance(quiz_instance.votes[option], int):  # Ensure it's an integer
                vote_count = quiz_instance.votes[option]
                percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0
                result_table += f"{option.ljust(12)} | {str(vote_count).ljust(5)} | {percentage:.2f}%\n"
        
        await ctx.send(f"```{result_table}```")
    
    # Move to the next question
    await send_question(ctx, quiz_instance)



@bot.command()
async def upload_quiz(ctx):
    if not ctx.message.attachments:
        await ctx.send("Please attach a JSON file with the quiz data.")
        return
    
    attachment = ctx.message.attachments[0]
    if not attachment.filename.endswith(".json"):
        await ctx.send("The file must be a JSON file.")
        return
    
    file_content = await attachment.read()
    try:
        new_quiz_data = json.loads(file_content)
    except json.JSONDecodeError:
        await ctx.send("Invalid JSON file.")
        return
    
    for quiz_name, quiz_content in new_quiz_data.items():
        quiz_data[quiz_name] = quiz_content
    
    save_quiz_data()
    await ctx.send("Quiz data uploaded and updated successfully!")

@bot.command()
async def force_quit(ctx):
    channel_id = ctx.channel.id

    # Check if the user has "Manage Messages" permission or is the bot owner
    if not ctx.author.guild_permissions.manage_messages and ctx.author.id != bot.owner_id:
        await ctx.send("You do not have permission to force quit quizzes in this channel.")
        return

    if channel_id in quizzes:
        del quizzes[channel_id]
        await ctx.send("All quizzes in this channel have been forcefully ended.")
    else:
        await ctx.send("No active quiz in this channel.")


print("Started")
bot.run(os.getenv("DISCORD_TOKEN"))