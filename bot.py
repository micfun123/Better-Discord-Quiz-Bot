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
    def __init__(self, quiz_name, quiz_starter_id):
        self.quiz_name = quiz_name
        self.quiz_starter_id = quiz_starter_id
        self.current_question_index = -1
        self.votes = {}

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

        if user_id in quiz_instance.votes:
            prev_vote = quiz_instance.votes[user_id]
            quiz_instance.votes[prev_vote] -= 1

        quiz_instance.votes[user_id] = self.label
        quiz_instance.votes[self.label] = quiz_instance.votes.get(self.label, 0) + 1
        await interaction.response.send_message(
            f"You voted for {self.label}", ephemeral=True
        )


@bot.command()
async def start_quiz(ctx, quiz_name: str):
    if quiz_name not in quiz_data:
        await ctx.send("Quiz not found.")
        return

    channel_id = ctx.channel.id
    if channel_id in quizzes:
        await ctx.send("A quiz is already running in this channel.")
        return

    quizzes[channel_id] = Quiz(quiz_name, ctx.author.id)
    await ctx.send(f"Quiz '{quiz_name}' is ready. Use `!next_question` to start.")


async def send_question(ctx, quiz_instance):
    if (
        quiz_instance.current_question_index
        >= len(quiz_data[quiz_instance.quiz_name]["questions"]) - 1
    ):
        await ctx.send("The quiz has ended!")
        del quizzes[ctx.channel.id]
        return

    quiz_instance.current_question_index += 1
    question_data = quiz_instance.get_current_question()
    question = question_data["question"]
    options = question_data["options"]

    if len(options) < 2:
        await ctx.send("You need at least two options.")
        return

    view = QuizView(options, quiz_instance)
    await ctx.send(
        f"**Question {quiz_instance.current_question_index + 1}: {question}**",
        view=view,
    )


@bot.command()
async def next_question(ctx):
    channel_id = ctx.channel.id
    if channel_id not in quizzes:
        await ctx.send(
            "No quiz is currently running in this channel. Use `!start_quiz <quiz_name>` to start a quiz."
        )
        return

    quiz_instance = quizzes[channel_id]
    if ctx.author.id != quiz_instance.quiz_starter_id:
        await ctx.send("Only the quiz starter can move to the next question.")
        return

    total_votes = sum(v for k, v in quiz_instance.votes.items() if isinstance(v, int))
    if total_votes != 0:
        await ctx.send("Results | Count | % :")
        for option in quiz_instance.votes:
            if isinstance(quiz_instance.votes[option], int):
                await ctx.send(
                    f"{option} | {quiz_instance.votes[option]} | {quiz_instance.votes[option] / total_votes * 100:.2f}%"
                )

    # Reset votes for the next question
    quiz_instance.votes = {}
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


print("Started")
bot.run(os.getenv("DISCORD_TOKEN"))
