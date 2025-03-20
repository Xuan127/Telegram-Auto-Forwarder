"""
Example configuration settings for the Telegram Auto Forwarder.
Copy this file to config.py and fill in your own values.
"""
import os
from typing import List

# Telegram API credentials
# Get these from https://my.telegram.org/apps
API_ID = 'YOUR_API_ID'
API_HASH = 'YOUR_API_HASH'
PHONE_NUMBER = 'YOUR_PHONE_NUMBER'  # With country code, e.g. '+1234567890'

# Source and target configuration
# Each source can be a channel username, group username, or chat ID
SOURCE_CHATS: List[str] = ['channel_username1', 'group_username2']  # Source chat identifiers
# Target chat ID to forward messages to (can be a channel, group, or private chat)
FORWARD_CHAT_ID: int = 0

# File paths for persistent storage
SESSION_NAME: str = 'session_name'  # Name for the Telethon session file
STATE_FILE: str = 'channel_states.json'  # File to store channel states
MESSAGE_HASH_FILE: str = 'message_hashes.json'  # File to store message hashes

# OpenRouter API configuration
# Get this from https://openrouter.ai/keys
OPENROUTER_API_KEY: str = "YOUR_OPENROUTER_API_KEY"

# Message processing configuration
MESSAGE_HASH_STORE_SIZE: int = 1000  # Size of the circular buffer for message hashes
GROUP_PROCESSING_DELAY: int = 2  # Delay in seconds before processing grouped messages
POLLING_INTERVAL: int = 10  # Interval in seconds between polling for new messages
