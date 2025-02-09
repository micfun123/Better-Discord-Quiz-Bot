# Discord Quiz Bot

This is a Discord bot designed to facilitate interactive quizzes within a Discord server. The bot allows users to start quizzes, answer questions, and view results in real-time. It supports multiple quizzes, each defined by a JSON file, and provides a user-friendly interface for managing and participating in quizzes.

## Features

-   **Start Quizzes**: Users can start a quiz by specifying the quiz name.
    
-   **Multiple Quizzes**: The bot supports multiple quizzes, each with its own set of questions and options.
    
-   **Interactive Buttons**: Users can vote on quiz questions using interactive buttons.
    
-   **Real-Time Results**: The bot displays real-time results after each question.
    
-   **Quiz Upload**: Admins can upload new quizzes via JSON files.
    

## Setup

### Prerequisites

-   Python 3.8 or higher
    
-   A Discord bot token
    
-   `py-cord` library
    
-   `python-dotenv` library
    

### Installation

1.  **Clone the Repository**:
    
    ```
    git clone https://github.com/micfun123/Better-Discord-Quiz-Bot.git
    cd Better-Discord-Quiz-Bot
    ```
    
2.  **Install Dependencies**:

    `pip install -r requirements.txt` 
    
3.  **Set Up Environment Variables**:  
    Create a `.env` file in the root directory and add your Discord bot token:   
    ` DISCORD_TOKEN=your_discord_bot_token_here` 
    
4.  **Run the Bot**:
      
    `python bot.py` 
    

## Usage

### Commands

-   **`!start_quiz <quiz_name>`**: Starts a quiz with the specified name.
    
-   **`!next_question`**: Moves to the next question in the quiz. Only the quiz starter can use this command.
    
-   **`!upload_quiz`**: Uploads a new quiz via a JSON file attachment.
    

### Quiz JSON Format

Quizzes are defined in JSON files. Each quiz should have the following structure:

```json
{
  "quiz_name": {
    "questions": [
      {
        "question": "What is the capital of France?",
        "options": ["Paris", "London", "Berlin", "Madrid"]
      },
      {
        "question": "What is 2 + 2?",
        "options": ["3", "4", "5", "6"]
      }
    ]
  }
}
```

### Example

1.  **Start a Quiz**:
    ```
    !start_quiz general_knowledge
    ```
2.  **Answer Questions**:  
    The bot will post questions with interactive buttons for each option. Users can click on the buttons to vote.
    
3.  **Move to the Next Question**:
    
    ```
    !next_question 
    ```
4.  **Upload a New Quiz**:  
    Attach a JSON file with the quiz data and use the command:
	
	   ` !upload_quiz` 
   
  

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request with your changes or donations on the Buy Me a Coffee 
[Buy Me A TEA](https://www.buymeacoffee.com/Michaelrbparker)
