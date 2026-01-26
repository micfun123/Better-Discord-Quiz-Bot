# pylint: disable=missing-docstring

"""Discord Quiz Bot - Interactive quiz system for Discord servers."""

import json
import logging
import os
from typing import TypedDict

import discord
from discord import Interaction, InteractionMessage, app_commands
from discord.ext import commands
from discord.ui import Button, View
from dotenv import load_dotenv


log = logging.getLogger()
load_dotenv()


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# Max option length for results table
MAX_OPTION_LENGTH = 15
# Minimum option length for results table, 6 to match "Option "
MIN_OPTION_LENGTH = 6


class QuizQuestion(TypedDict):
    question: str
    options: list[str]


class QuizData(TypedDict):
    questions: list[QuizQuestion]


def load_quiz_data() -> dict[str, QuizData]:
    """Load quiz data from a JSON file."""
    if os.path.exists("quiz_data.json"):  # Check if the file exists
        with open("quiz_data.json", "r", encoding="utf-8") as file:
            return json.load(file)  # Load and return the JSON data
    return {}


def save_quiz_data() -> None:
    """Save quiz data to the JSON file."""
    with open("quiz_data.json", "w", encoding="utf-8") as file:
        json.dump(quiz_data, file, indent=4)


quiz_data = load_quiz_data()

# Dictionary to store active quizzes by channel ID
quizzes: dict[int, "Quiz"] = {}


class Quiz:
    """Represents a quiz instance with questions, votes, and state tracking."""

    def __init__(
        self, quiz_name: str, quiz_starter_id: int, allow_multiple_answers: bool = False
    ):
        self.quiz_name: str = quiz_name  # Name of the quiz
        self.quiz_starter_id: int = (
            quiz_starter_id  # ID of the user who started the quiz
        )
        self.current_question_index = -1  # Track the current question index
        self.user_votes: dict[int, set[str]] = {}  # Store votes for each option
        self.answer_votes: dict[str, int] = {}
        self.allow_multiple_answers: bool = (
            allow_multiple_answers  # Allow multiple answers per user
        )
        self.current_view: QuizView | None = (
            None  # Store the current View (buttons) for the quiz
        )
        self.current_question_votes = (
            0  # Store the number of votes for the current question
        )
        self.votes_message: discord.WebhookMessage | None = (
            None  # Store the message displaying the number of votes
        )
        self.last_message_id: int | None = None  # Store the last message ID

    def get_current_question(self) -> QuizQuestion | None:
        """Get the current question based on the index."""
        if self.current_question_index < len(quiz_data[self.quiz_name]["questions"]):
            return quiz_data[self.quiz_name]["questions"][self.current_question_index]
        return None


class QuizView(View):
    """Custom View to display quiz buttons."""

    def __init__(self, options: list[str], quiz_instance: Quiz) -> None:
        super().__init__()
        self.options = options
        self.quiz_instance = quiz_instance  # Reference to the Quiz instance
        for option in options:
            self.add_item(QuizButton(label=option, parent_view=self))


class QuizButton(Button[QuizView]):
    """Custom Button for quiz options."""

    def __init__(self, label: str, parent_view: QuizView) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.parent_view = parent_view

    # Callback when a button is clicked
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        assert self.label is not None, "'self.label' should not be None"

        user_id = interaction.user.id
        quiz_instance = self.parent_view.quiz_instance

        # Handle multiple answers if allowed
        if quiz_instance.allow_multiple_answers:
            if user_id not in quiz_instance.user_votes:
                quiz_instance.user_votes[user_id] = set()

            # Toggle the vote for the selected option
            if self.label in quiz_instance.user_votes[user_id]:
                quiz_instance.user_votes[user_id].remove(self.label)
                quiz_instance.answer_votes[self.label] = (
                    quiz_instance.answer_votes.get(self.label, 0) - 1
                )
            else:
                quiz_instance.user_votes[user_id].add(self.label)
                quiz_instance.answer_votes[self.label] = (
                    quiz_instance.answer_votes.get(self.label, 0) + 1
                )
        else:
            # Handle single answer per user
            if user_id in quiz_instance.user_votes:
                quiz_instance.user_votes.pop(user_id)

            # Record the new vote
            quiz_instance.user_votes[user_id] = {self.label}
            quiz_instance.answer_votes[self.label] = (
                quiz_instance.answer_votes.get(self.label, 0) + 1
            )

        # Update the total number of votes for the current question
        quiz_instance.current_question_votes = sum(
            v for v in quiz_instance.answer_votes.values()
        )

        # Update the votes message
        if quiz_instance.votes_message:
            await quiz_instance.votes_message.edit(
                content=f"Votes: {quiz_instance.current_question_votes}"
            )

        # Send a confirmation message to the user
        await interaction.followup.send(
            content=f"You voted for {self.label}", ephemeral=True
        )


def has_permission(author: discord.User | discord.Member, permission: str) -> bool:
    has_perm: bool = False

    if isinstance(author, discord.Member):
        has_perm = getattr(author.guild_permissions, permission, has_perm)

    return has_perm


@bot.event
async def on_ready():
    log.info("Logged in as %s", bot.user)
    log.info("Guilds: %s", [g.id for g in bot.guilds])

    try:
        # bot.tree.copy_global_to(guild=TEST_GUILD)
        cmds = await bot.tree.sync()
        log.info("Registered %s commands", len(cmds))
    except Exception as e:  # pylint: disable=broad-exception-caught
        log.error("Failed to sync commands: %s", e)


@bot.tree.command(name="start_quiz", description="Start a quiz")
@app_commands.describe(
    quiz_name="The name of the quiz to start",
    multiple_answers="Whether multiple answers are allowed (true/false)",
)
async def start_quiz(
    interaction: discord.Interaction,
    quiz_name: str,
    multiple_answers: bool = False,
):
    """
    Start a quiz with the given name.
    Set allow_multiple_answers to 'true' for multiple choice.
    """
    if quiz_name not in quiz_data:  # Check if the quiz exists
        await interaction.response.send_message("Quiz not found.")
        return

    assert interaction.channel_id is not None, (
        "'channel_id' should exist on interaction"
    )
    if (
        interaction.channel_id in quizzes
    ):  # Check if a quiz is already running in the channel
        await interaction.response.send_message(
            "A quiz is already running in this channel."
        )
        return

    # Create a new Quiz instance and store it
    quizzes[interaction.channel_id] = Quiz(
        quiz_name, interaction.user.id, multiple_answers
    )
    await send_question(
        interaction, quizzes[interaction.channel_id]
    )  # Send the first question


async def send_question(interaction: discord.Interaction, quiz_instance: Quiz):
    """Send the next question in the quiz to the channel."""
    assert interaction.channel_id is not None, (
        "'channel_id' should exist on interaction"
    )

    quiz_instance.current_question_index += 1

    # Check if the quiz has ended
    if quiz_instance.current_question_index >= len(
        quiz_data[quiz_instance.quiz_name]["questions"]
    ):
        await interaction.followup.send("The quiz has ended!")
        del quizzes[interaction.channel_id]
        return

    # Get the current question data
    question_data = quiz_instance.get_current_question()
    if question_data is None:
        await interaction.followup.send("End of questions")
        return

    question: str = (
        question_data["question"]
        .replace("\n", "\n")
        .replace("\r", " ")
        .replace("\t", " ")
    )
    options = question_data["options"]

    if len(options) < 2:
        await interaction.followup.send("You need at least two options.")
        return

    # Reset votes for the new question
    quiz_instance.answer_votes = {option: 0 for option in options}
    quiz_instance.current_question_votes = 0
    view = QuizView(options, quiz_instance)
    quiz_instance.current_view = view  # Store the View for later use

    content = f"**Question {quiz_instance.current_question_index + 1}: {question}**"
    if interaction.response.is_done():
        message = await interaction.followup.send(
            content,
            view=view,
            wait=True,
        )
    else:
        response = await interaction.response.send_message(content, view=view)
        message = response.resource
        assert isinstance(message, InteractionMessage), "Invalid message type"

    log.info("Message id: %s", message.id)
    quiz_instance.last_message_id = message.id

    votes_message = await interaction.followup.send("Votes: 0", wait=True)
    quiz_instance.votes_message = votes_message


@bot.tree.command(name="next_question")
async def next_question(interaction: Interaction):
    """Move to the next question in the quiz."""
    assert interaction.channel_id is not None, (
        "'channel_id' should exist on interaction"
    )

    if interaction.channel_id not in quizzes:
        await interaction.response.send_message(
            "No quiz is currently running in this channel. "
            "Use `!start_quiz <quiz_name>` to start a quiz."
        )
        return

    quiz_instance = quizzes[interaction.channel_id]

    # Ensure only the quiz starter can move to the next question
    if interaction.user.id != quiz_instance.quiz_starter_id:
        await interaction.response.send_message(
            "Only the quiz starter can move to the next question."
        )
        return

    # Disable the buttons in the previous question's message
    if quiz_instance.last_message_id is not None:
        assert isinstance(interaction.channel, discord.TextChannel), (
            "'channel' should exist on interaction"
        )

        try:
            log.info("Last message id: %s", quiz_instance.last_message_id)

            previous_message = await interaction.channel.fetch_message(
                quiz_instance.last_message_id
            )

            assert quiz_instance.current_view is not None, (
                "'curent_view' should not be None"
            )

            for item in quiz_instance.current_view.children:
                item.disabled = True  # type: ignore | 'disabled' is a valid attribute
            await previous_message.edit(
                view=quiz_instance.current_view
            )  # Edit the message to disable buttons
        except discord.NotFound:
            await interaction.response.send_message(
                "Could not find the previous message to disable buttons."
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to edit the previous message."
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            log.error(e)
            await interaction.response.send_message(
                "Unhandled server error, please contact the admin if issue persists"
            )
            return

    # Display results if at least one question has been asked
    if quiz_instance.current_question_index >= 0:
        total_votes: int = sum(quiz_instance.answer_votes.values())

        # Find longest quiz option (for result table formatting)
        longest_option_length = MIN_OPTION_LENGTH
        for option in quiz_instance.answer_votes:
            longest_option_length = max(len(option), longest_option_length)
            if longest_option_length >= MAX_OPTION_LENGTH:
                longest_option_length = MAX_OPTION_LENGTH
                break

        # Spaces for option portion of table
        option_spaces = max(MIN_OPTION_LENGTH, longest_option_length)
        # Build header + seperator based on option length
        result_table = (
            "Results\nOption "
            + " " * max(longest_option_length - MIN_OPTION_LENGTH, 0)
            + "| Count | %\n"
        )
        result_table += "-" * (16 + option_spaces) + "\n"

        for option in quiz_instance.answer_votes:
            vote_count = quiz_instance.answer_votes[option]
            percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0
            if len(option) > MAX_OPTION_LENGTH:
                option = (
                    option[: MAX_OPTION_LENGTH - 3] + "..."
                )  # Truncate long options
            result_table += f"{option.ljust(option_spaces)}"
            result_table += f" | {str(vote_count).ljust(5)} | {percentage:.2f}%\n"

        content = f"```{result_table}```"
        if interaction.response.is_done():
            await interaction.followup.send(content)
        else:
            await interaction.response.send_message(content)

    # Move to the next question
    await send_question(interaction, quiz_instance)


@bot.command()
async def upload_quiz(ctx: commands.Context[commands.Bot]):
    """Upload a new quiz via a JSON file attachment."""
    if not ctx.message.attachments:
        await ctx.send("Please attach a JSON file with the quiz data.")
        return

    attachment = ctx.message.attachments[0]
    if not attachment.filename.endswith(".json"):
        await ctx.send("The file must be a JSON file.")
        return

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


@bot.tree.command(name="force_quit")
async def force_quit(interaction: Interaction):
    """Forcefully quit any active quiz in the channel."""

    if (
        not has_permission(interaction.user, "manage_messages")
        and interaction.user.id != bot.owner_id
    ):
        await interaction.response.send_message(
            "You do not have permission to force quit quizzes in this channel."
        )
        return

    if interaction.channel_id in quizzes:  # Check if a quiz is running in the channel
        del quizzes[interaction.channel_id]  # Remove the quiz
        await interaction.response.send_message(
            "All quizzes in this channel have been forcefully ended."
        )
    else:
        await interaction.response.send_message("No active quiz in this channel.")


def main():
    discord.utils.setup_logging()

    # Start the bot
    log.info("Starting...")
    token = os.getenv("DISCORD_TOKEN")
    if token is None:
        raise ValueError("DISCORD_TOKEN environment variable is not set")

    bot.run(token)


if __name__ == "__main__":
    main()
