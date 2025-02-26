import discord
import json
import os
from discord.ext import commands
from discord.ui import View, Button
from dotenv import load_dotenv


load_dotenv()


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="+", intents=intents)


# Load quiz data from a JSON file
def load_quiz_data():
    if os.path.exists("quiz_data.json"):  # Check if the file exists
        with open("quiz_data.json", "r") as file:
            return json.load(file)  # Load and return the JSON data
    return {}  # Return an empty dictionary if the file doesn't exist


# Save quiz data to the JSON file
def save_quiz_data():
    with open("quiz_data.json", "w") as file:
        json.dump(quiz_data, file, indent=4)  # Write the data with pretty formatting


# Load quiz data at startup
quiz_data = load_quiz_data()

# Dictionary to store active quizzes by channel ID
quizzes = {}


# Quiz class to manage quiz state
class Quiz:
    def __init__(self, quiz_name, quiz_starter_id, allow_multiple_answers=False):
        self.quiz_name = quiz_name  # Name of the quiz
        self.quiz_starter_id = quiz_starter_id  # ID of the user who started the quiz
        self.current_question_index = -1  # Track the current question index
        self.votes = {}  # Store votes for each option
        self.allow_multiple_answers = allow_multiple_answers  # Allow multiple answers per user
        self.current_view = None  # Store the current View (buttons) for the quiz
        self.current_question_votes = 0  # Store the number of votes for the current question
        self.votes_message = None  # Store the message displaying the number of votes

    # Get the current question based on the index
    def get_current_question(self):
        if self.current_question_index < len(quiz_data[self.quiz_name]["questions"]):
            return quiz_data[self.quiz_name]["questions"][self.current_question_index]
        return None


# Custom View to display quiz buttons
class QuizView(View):
    def __init__(self, options, quiz_instance):
        super().__init__()
        self.options = options  # List of answer options
        self.quiz_instance = quiz_instance  # Reference to the Quiz instance
        for option in options:
            self.add_item(QuizButton(label=option, parent_view=self))


# Custom Button for quiz options
class QuizButton(Button):
    def __init__(self, label, parent_view):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.parent_view = parent_view

    # Callback when a button is clicked
    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        quiz_instance = self.parent_view.quiz_instance

        # Handle multiple answers if allowed
        if quiz_instance.allow_multiple_answers:
            if user_id not in quiz_instance.votes:
                quiz_instance.votes[user_id] = set()  # Initialize a set for user's votes

            # Toggle the vote for the selected option
            if self.label in quiz_instance.votes[user_id]:
                quiz_instance.votes[user_id].remove(self.label)
                quiz_instance.votes[self.label] = quiz_instance.votes.get(self.label, 0) - 1
            else:
                quiz_instance.votes[user_id].add(self.label)
                quiz_instance.votes[self.label] = quiz_instance.votes.get(self.label, 0) + 1
        else:
            # Handle single answer per user
            if user_id in quiz_instance.votes:
                prev_vote = quiz_instance.votes[user_id]
                if isinstance(prev_vote, str):
                    quiz_instance.votes[prev_vote] -= 1  # Remove the previous vote

            # Record the new vote
            quiz_instance.votes[user_id] = self.label
            quiz_instance.votes[self.label] = quiz_instance.votes.get(self.label, 0) + 1

        # Update the total number of votes for the current question
        quiz_instance.current_question_votes = sum(
            v for v in quiz_instance.votes.values() if isinstance(v, int)
        )

        # Update the votes message
        if quiz_instance.votes_message:
            await quiz_instance.votes_message.edit(
                content=f"Votes: {quiz_instance.current_question_votes}"
            )

        # Send a confirmation message to the user
        await interaction.response.send_message(f"You voted for {self.label}", ephemeral=True)


@bot.command()
async def start_quiz(ctx, quiz_name: str, allow_multiple_answers: bool = False):
    if quiz_name not in quiz_data:  # Check if the quiz exists
        await ctx.send("Quiz not found.")
        return

    channel_id = ctx.channel.id
    if channel_id in quizzes:  # Check if a quiz is already running in the channel
        await ctx.send("A quiz is already running in this channel.")
        return

    # Create a new Quiz instance and store it
    quizzes[channel_id] = Quiz(quiz_name, ctx.author.id, allow_multiple_answers)
    await send_question(ctx, quizzes[channel_id])  # Send the first question


async def send_question(ctx, quiz_instance):
    quiz_instance.current_question_index += 1  # Move to the next question

    # Check if the quiz has ended
    if quiz_instance.current_question_index >= len(quiz_data[quiz_instance.quiz_name]["questions"]):
        await ctx.send("The quiz has ended!")
        del quizzes[ctx.channel.id]  # Remove the quiz from active quizzes
        return

    # Get the current question data
    question_data = quiz_instance.get_current_question()
    question = question_data["question"].replace("\n", "\n").replace("\r", " ").replace("\t", " ")
    options = question_data["options"]

    # Ensure there are at least two options
    if len(options) < 2:
        await ctx.send("You need at least two options.")
        return

    # Reset votes for the new question
    quiz_instance.votes = {option: 0 for option in options}
    quiz_instance.current_question_votes = 0  # Reset the vote count for the new question

    # Create a new View with buttons for the options
    view = QuizView(options, quiz_instance)
    quiz_instance.current_view = view  # Store the View for later use

    # Send the question and buttons to the channel
    message = await ctx.send(f"**Question {quiz_instance.current_question_index + 1}: {question}**", view=view)
    quiz_instance.last_message_id = message.id  # Store the message ID for later editing

    # Send a message to display the number of votes
    votes_message = await ctx.send("Votes: 0")
    quiz_instance.votes_message = votes_message  


@bot.command()
async def next_question(ctx):
    channel_id = ctx.channel.id
    if channel_id not in quizzes: 
        await ctx.send("No quiz is currently running in this channel. Use `+start_quiz <quiz_name>` to start a quiz.")
        return

    quiz_instance = quizzes[channel_id]

    # Ensure only the quiz starter can move to the next question
    if ctx.author.id != quiz_instance.quiz_starter_id:
        await ctx.send("Only the quiz starter can move to the next question.")
        return

    # Disable the buttons in the previous question's message
    if hasattr(quiz_instance, 'last_message_id'):
        try:
            # Fetch the previous message
            previous_message = await ctx.channel.fetch_message(quiz_instance.last_message_id)
            if previous_message:
                # Disable all buttons in the previous message's view
                for item in quiz_instance.current_view.children:
                    item.disabled = True
                await previous_message.edit(view=quiz_instance.current_view)  # Edit the message to disable buttons
        except discord.NotFound:
            await ctx.send("Could not find the previous message to disable buttons.")
        except discord.Forbidden:
            await ctx.send("I don't have permission to edit the previous message.")

    # Display results if at least one question has been asked
    if quiz_instance.current_question_index >= 0:
        total_votes = sum(v for v in quiz_instance.votes.values() if isinstance(v, int)) 
        result_table = "Results\nOption       | Count | %\n"
        result_table += "-" * 30 + "\n"

        # Build the results table
        for option in quiz_instance.votes:
            if isinstance(quiz_instance.votes[option], int): 
                vote_count = quiz_instance.votes[option]
                percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0
                result_table += f"{option.ljust(12)} | {str(vote_count).ljust(5)} | {percentage:.2f}%\n"

        await ctx.send(f"```{result_table}```")  

    # Move to the next question
    await send_question(ctx, quiz_instance)


# Command to upload a new quiz via a JSON file
@bot.command()
async def upload_quiz(ctx):
    if not ctx.message.attachments:  # Check if a file is attached
        await ctx.send("Please attach a JSON file with the quiz data.")
        return

    attachment = ctx.message.attachments[0]
    if not attachment.filename.endswith(".json"):  # Ensure the file is a JSON file
        await ctx.send("The file must be a JSON file.")
        return

    # Read the file content
    file_content = await attachment.read()
    try:
        new_quiz_data = json.loads(file_content)  # Parse the JSON data
    except json.JSONDecodeError:
        await ctx.send("Invalid JSON file.")
        return

    # Update the quiz data with the new content
    for quiz_name, quiz_content in new_quiz_data.items():
        quiz_data[quiz_name] = quiz_content

    save_quiz_data()  # Save the updated quiz data to the file
    await ctx.send("Quiz data uploaded and updated successfully!")


# Command to forcefully quit a quiz
@bot.command()
async def force_quit(ctx):
    channel_id = ctx.channel.id

    # Check if the user has "Manage Messages" permission or is the bot owner
    if not ctx.author.guild_permissions.manage_messages and ctx.author.id != bot.owner_id:
        await ctx.send("You do not have permission to force quit quizzes in this channel.")
        return

    if channel_id in quizzes:  # Check if a quiz is running in the channel
        del quizzes[channel_id]  # Remove the quiz
        await ctx.send("All quizzes in this channel have been forcefully ended.")
    else:
        await ctx.send("No active quiz in this channel.")


# Start the bot
print("Started")
bot.run(os.getenv("DISCORD_TOKEN"))