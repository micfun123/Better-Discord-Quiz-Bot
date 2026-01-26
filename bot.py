"""Discord Quiz Bot - Interactive quiz system for Discord servers."""
import os
import json
import asyncio
import discord
from discord.ext import commands
from discord.ui import View, Button
from dotenv import load_dotenv


load_dotenv()


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

MAX_OPTION_LENGTH = 15
MIN_OPTION_LENGTH = 6


def load_quiz_data():
    """Load quiz data from a JSON file."""
    if os.path.exists("quiz_data.json"):
        with open("quiz_data.json", "r", encoding="utf-8") as file:
            return json.load(file)
    return {}


def save_quiz_data():
    """Save quiz data to the JSON file."""
    with open("quiz_data.json", "w", encoding="utf-8") as file:
        json.dump(quiz_data, file, indent=4)


quiz_data = load_quiz_data()
quizzes = {}


class Quiz:
    """Represents a quiz instance with questions, votes, and state tracking."""
    def __init__(self, quiz_name, quiz_starter_id, allow_multiple_answers=False):
        self.quiz_name = quiz_name
        self.quiz_starter_id = quiz_starter_id
        self.current_question_index = -1
        self.votes = {}
        self.allow_multiple_answers = allow_multiple_answers
        self.current_view = None
        self.current_question_votes = 0
        self.votes_message = None
        self.last_message_id = None
        self.pending_vote_update = False
        self.update_lock = asyncio.Lock()
        self.last_vote_edit_time = 0

    def get_current_question(self):
        """Get the current question based on the index."""
        if self.current_question_index < len(quiz_data[self.quiz_name]["questions"]):
            return quiz_data[self.quiz_name]["questions"][self.current_question_index]
        return None

    async def schedule_vote_update(self):
        """Schedule a batched vote count update to avoid rate limits."""
        if self.pending_vote_update:
            return
        
        self.pending_vote_update = True
        await asyncio.sleep(2.0)
        
        async with self.update_lock:
            current_time = asyncio.get_event_loop().time()
            time_since_last_edit = current_time - self.last_vote_edit_time
            if time_since_last_edit < 2.0:
                await asyncio.sleep(2.0 - time_since_last_edit)
            
            if self.votes_message:
                try:
                    await self.votes_message.edit(
                        content=f"Votes: {self.current_question_votes}"
                    )
                    self.last_vote_edit_time = asyncio.get_event_loop().time()
                except discord.HTTPException:
                    pass
            self.pending_vote_update = False


class QuizView(View):
    """Custom View to display quiz buttons."""
    def __init__(self, options, quiz_instance):
        super().__init__(timeout=None)
        self.options = options
        self.quiz_instance = quiz_instance
        for option in options:
            self.add_item(QuizButton(label=option, parent_view=self))


class QuizButton(Button):
    """Custom Button for quiz options."""
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
                quiz_instance.votes[self.label] = (
                    quiz_instance.votes.get(self.label, 0) - 1
                )
                response_text = f"❌ Removed vote for **{self.label}**"
            else:
                quiz_instance.votes[user_id].add(self.label)
                quiz_instance.votes[self.label] = (
                    quiz_instance.votes.get(self.label, 0) + 1
                )
                response_text = f"✅ Voted for **{self.label}**"
        else:
            if user_id in quiz_instance.votes:
                prev_vote = quiz_instance.votes[user_id]
                if isinstance(prev_vote, str):
                    quiz_instance.votes[prev_vote] -= 1

            quiz_instance.votes[user_id] = self.label
            quiz_instance.votes[self.label] = quiz_instance.votes.get(self.label, 0) + 1
            response_text = f"✅ Voted for **{self.label}**"

        quiz_instance.current_question_votes = sum(
            v for v in quiz_instance.votes.values() if isinstance(v, int)
        )

        asyncio.create_task(quiz_instance.schedule_vote_update())

        # Send ephemeral response but suppress errors if rate limited
        try:
            await interaction.response.send_message(response_text, ephemeral=True)
        except discord.HTTPException:
            # If rate limited, just acknowledge without message
            try:
                await interaction.response.defer(ephemeral=True, thinking=False)
            except:
                pass


@bot.command()
async def start_quiz(
        ctx: commands.Context,
        quiz_name: str,
        allow_multiple_answers: str = "false"
    ):
    """
    Start a quiz with the given name.
    Set allow_multiple_answers to 'true' for multiple choice.
    """
    has_permission = (
        hasattr(ctx.author, 'guild_permissions') and
        ctx.author.guild_permissions.administrator
    )
    if not has_permission and ctx.author.id != bot.owner_id:
        await ctx.send("You need administrator permissions to start a quiz.")
        return

    multiple_answers = allow_multiple_answers.lower() in ("true", "yes", "1")
    if quiz_name not in quiz_data:
        await ctx.send("Quiz not found.")
        return

    channel_id = ctx.channel.id
    if channel_id in quizzes:
        await ctx.send("A quiz is already running in this channel.")
        return

    quizzes[channel_id] = Quiz(quiz_name, ctx.author.id, multiple_answers)
    await send_question(ctx, quizzes[channel_id])


async def send_question(ctx: commands.Context, quiz_instance: Quiz):
    """Send the next question in the quiz to the channel."""
    quiz_instance.current_question_index += 1

    if quiz_instance.current_question_index >= len(
        quiz_data[quiz_instance.quiz_name]["questions"]
    ):
        await ctx.send("The quiz has ended!")
        del quizzes[ctx.channel.id]
        return

    question_data = quiz_instance.get_current_question()
    question = (
        question_data["question"]
        .replace("\n", "\n")
        .replace("\r", " ")
        .replace("\t", " ")
    )
    options = question_data["options"]

    if len(options) < 2:
        await ctx.send("You need at least two options.")
        return

    quiz_instance.votes = {option: 0 for option in options}
    quiz_instance.current_question_votes = 0
    view = QuizView(options, quiz_instance)
    quiz_instance.current_view = view

    message = await ctx.send(
        f"**Question {quiz_instance.current_question_index + 1}: {question}**",
        view=view,
    )
    quiz_instance.last_message_id = message.id

    votes_message = await ctx.send("Votes: 0")
    quiz_instance.votes_message = votes_message


@bot.command()
async def next_question(ctx: commands.Context):
    """Move to the next question in the quiz."""
    channel_id = ctx.channel.id
    if channel_id not in quizzes:
        await ctx.send(
            "No quiz is currently running in this channel. "
            "Use `!start_quiz <quiz_name>` to start a quiz."
        )
        return

    quiz_instance = quizzes[channel_id]

    if ctx.author.id != quiz_instance.quiz_starter_id:
        await ctx.send("Only the quiz starter can move to the next question.")
        return

    if hasattr(quiz_instance, "last_message_id") and quiz_instance.current_view:
        try:
            await asyncio.sleep(1.0)
            previous_message = await ctx.channel.fetch_message(
                quiz_instance.last_message_id
            )
            if previous_message:
                for item in quiz_instance.current_view.children:
                    item.disabled = True
                await previous_message.edit(view=quiz_instance.current_view)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    if quiz_instance.current_question_index >= 0:
        total_votes = sum(v for v in quiz_instance.votes.values() if isinstance(v, int))

        longest_option_length = MIN_OPTION_LENGTH
        for option in quiz_instance.votes:
            if isinstance(quiz_instance.votes[option], int):
                longest_option_length = max(len(option), longest_option_length)
                if longest_option_length >= MAX_OPTION_LENGTH:
                    longest_option_length = MAX_OPTION_LENGTH
                    break

        option_spaces = max(MIN_OPTION_LENGTH, longest_option_length)
        result_table = (
            "Results\nOption "
            + " " * max(longest_option_length - MIN_OPTION_LENGTH, 0)
            + "| Count | %\n"
        )
        result_table += "-" * (16 + option_spaces) + "\n"

        for option in quiz_instance.votes:
            if isinstance(quiz_instance.votes[option], int):
                vote_count = quiz_instance.votes[option]
                percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0
                if len(option) > MAX_OPTION_LENGTH:
                    option = option[: MAX_OPTION_LENGTH - 3] + "..."
                result_table += f"{option.ljust(option_spaces)}"
                result_table += f" | {str(vote_count).ljust(5)} | {percentage:.2f}%\n"

        await ctx.send(f"```{result_table}```")

    await send_question(ctx, quiz_instance)


@bot.command()
async def upload_quiz(ctx: commands.Context):
    """Upload a new quiz via a JSON file attachment."""
    has_permission = (
        hasattr(ctx.author, 'guild_permissions') and
        ctx.author.guild_permissions.administrator
    )
    if not has_permission and ctx.author.id != bot.owner_id:
        await ctx.send("You need administrator permissions to upload quizzes.")
        return

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
async def force_quit(ctx: commands.Context):
    """Forcefully quit any active quiz in the channel."""
    channel_id = ctx.channel.id

    has_permission = (
        hasattr(ctx.author, 'guild_permissions') and
        ctx.author.guild_permissions.manage_messages
    )
    if not has_permission and ctx.author.id != bot.owner_id:
        await ctx.send(
            "You do not have permission to force quit quizzes in this channel."
        )
        return

    if channel_id in quizzes:
        del quizzes[channel_id]
        await ctx.send("All quizzes in this channel have been forcefully ended.")
    else:
        await ctx.send("No active quiz in this channel.")


print("Started")
token = os.getenv("DISCORD_TOKEN")
if token is None:
    raise ValueError("DISCORD_TOKEN environment variable is not set")
bot.run(token)
