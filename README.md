# Telegram Auto Forwarder

An automated tool for monitoring Telegram channels and groups, filtering messages with AI, and forwarding interesting content to a target chat.

## Features

- Monitor multiple Telegram channels and groups
- Filter messages using AI (OpenRouter/Gemini)
- Forward interesting messages to a target chat
- Support for both regular and media group messages
- Persistent state storage to avoid duplicate messages
- Proper logging

## Setup

### 1. Install Dependencies

```bash
pip install telethon requests
```

### 2. Create Configuration

Copy the example configuration and fill it with your values:

```bash
cp config.example.py config.py
```

Then edit `config.py` with your:
- Telegram API credentials (from https://my.telegram.org/apps)
- Source chats to monitor
- Target chat for forwarding
- OpenRouter API key (from https://openrouter.ai/keys)

### 3. Find Your Chats

To easily get a list of all your channels and groups with their IDs, run:

```bash
python list_chats.py
```

This will:
- Connect to your Telegram account
- Generate a text file (`telegram_chats.txt`) with all your chats and their IDs
- Create a JSON file (`telegram_chats.json`) with the same data
- Display sample configuration entries

Use the output to update your `config.py` file with the correct chat identifiers.

## Running the Forwarder

Start the forwarder with:

```bash
python main.py
```

The script will:
1. Connect to your Telegram account
2. Initialize all source chats
3. Start monitoring for new messages
4. Filter messages using AI
5. Forward interesting messages to your target chat

## How It Works

### Monitoring Different Chat Types

- **Channels**: Uses the Telegram PTS (Point of Truth Sequence) for tracking updates
- **Groups**: Tracks message IDs to fetch only new messages

### Message Filtering

Messages are filtered using the Gemini AI model through OpenRouter API. 
The AI evaluates message content according to rules defined in the `AIFilter` class.

### State Management

The forwarder maintains persistent state to:
- Track channel/group update markers
- Store message hashes to prevent duplicate processing

## File Structure

- `main.py` - Entry point and orchestration
- `config.py` - Configuration settings
- `logger.py` - Logging system
- `state_manager.py` - State persistence
- `telegram_client.py` - Telegram client operations
- `ai_filter.py` - AI-based message filtering
- `list_chats.py` - Utility to list all chats and IDs
