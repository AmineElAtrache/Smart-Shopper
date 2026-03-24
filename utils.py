"""
utils.py
────────
Utility functions for logging, file operations, etc.
"""

import os
from datetime import datetime
from telegram import User


def log_user_query(user: User, query: str, response: str = None) -> None:
    """
    Save user query to a log file with user info and timestamp.
    
    Args:
        user: Telegram User object
        query: The message text the user sent
        response: Optional response from the bot
    """
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, "user_queries.txt")
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_id = user.id
    user_name = user.first_name or "Unknown"
    username = user.username or "N/A"
    
    # Format the log entry
    log_entry = f"""
{'='*80}
Timestamp:  {timestamp}
User ID:    {user_id}
Name:       {user_name}
Username:   @{username}
Query:      {query}
"""
    
    if response:
        log_entry += f"Response:   {response[:200]}..."  # First 200 chars of response
    
    # Append to file
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(log_entry + "\n")


def log_user_interaction(user: User, query: str, entities: dict, response: str = None) -> None:
    """
    Log detailed user interaction with NER entities.
    
    Args:
        user: Telegram User object
        query: The original query
        entities: Dictionary with extracted entities (product, brand, price, city, etc.)
        response: Optional response text
    """
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, "user_interactions.txt")
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_id = user.id
    user_name = user.first_name or "Unknown"
    username = user.username or "N/A"
    
    # Format entities for display
    entities_text = "\n".join([
        f"  • {key}: {value}"
        for key, value in entities.items()
        if value and key != "raw"
    ])
    
    # Format the log entry
    log_entry = f"""
{'='*80}
Timestamp:  {timestamp}
User ID:    {user_id}
Name:       {user_name}
Username:   @{username}

Original Query:
  {query}

Extracted Entities:
{entities_text if entities_text else "  (none detected)"}

"""
    
    if response:
        log_entry += f"Bot Response:\n  {response[:300]}\n"
    
    # Append to file
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(log_entry + "\n")
