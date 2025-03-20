"""
List Telegram Chats - A utility script for Telegram Auto Forwarder.

This script connects to your Telegram account and lists all channels and groups 
you have access to, along with their IDs and other identifying information.
The information is saved to a text file for easy reference when configuring
the Telegram Auto Forwarder.
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional

from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User, Dialog
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.functions.channels import GetFullChannelRequest

# Import config if available, otherwise use default values
try:
    import config
    API_ID = config.API_ID
    API_HASH = config.API_HASH
    PHONE_NUMBER = config.PHONE_NUMBER
    SESSION_NAME = config.SESSION_NAME
except ImportError:
    print("Config not found. Using default values.")
    API_ID = input("Enter your API ID: ")
    API_HASH = input("Enter your API hash: ")
    PHONE_NUMBER = input("Enter your phone number (with country code): ")
    SESSION_NAME = 'session_name'

# Output file
OUTPUT_FILE = 'telegram_chats.txt'
JSON_OUTPUT_FILE = 'telegram_chats.json'

async def fetch_chats():
    """Fetch all chats and channels the user has access to."""
    print(f"Connecting to Telegram with phone number {PHONE_NUMBER}...")
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start(phone=PHONE_NUMBER)
    
    print("Fetching dialogs...")
    dialogs = await client.get_dialogs()
    
    channels = []
    groups = []
    private_chats = []
    
    print("Processing dialogs...")
    for dialog in dialogs:
        entity = dialog.entity
        
        # Prepare basic info for all types
        chat_info = {
            'id': entity.id,
            'name': getattr(entity, 'title', None) or (
                f"{getattr(entity, 'first_name', '')} {getattr(entity, 'last_name', '')}".strip()
            ),
            'username': getattr(entity, 'username', None),
            'dialog_id': dialog.id,
        }
        
        # Categorize by type
        if isinstance(entity, Channel):
            if entity.broadcast:
                chat_info['type'] = 'channel'
                chat_info['participant_count'] = getattr(entity, 'participants_count', 'unknown')
                # Get more details for channels
                try:
                    full_channel = await client(GetFullChannelRequest(channel=entity))
                    chat_info['description'] = getattr(full_channel.full_chat, 'about', None)
                    chat_info['member_count'] = getattr(full_channel.full_chat, 'participants_count', None)
                except Exception as e:
                    print(f"Couldn't get full info for channel {chat_info['name']}: {e}")
                channels.append(chat_info)
            else:
                chat_info['type'] = 'supergroup'
                chat_info['participant_count'] = getattr(entity, 'participants_count', 'unknown')
                groups.append(chat_info)
        elif isinstance(entity, Chat):
            chat_info['type'] = 'group'
            chat_info['participant_count'] = getattr(entity, 'participants_count', 'unknown')
            groups.append(chat_info)
        elif isinstance(entity, User):
            chat_info['type'] = 'private'
            private_chats.append(chat_info)
    
    await client.disconnect()
    return channels, groups, private_chats

def write_to_text_file(channels, groups, private_chats):
    """Write chat information to a text file."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(f"TELEGRAM CHATS LIST - Generated on {now}\n")
        f.write("=" * 80 + "\n\n")
        
        f.write("CHANNELS\n")
        f.write("-" * 80 + "\n")
        for i, channel in enumerate(channels, 1):
            f.write(f"{i}. {channel['name']} (ID: {channel['id']})\n")
            if channel['username']:
                f.write(f"   Username: {channel['username']}\n")
            if channel.get('description'):
                f.write(f"   Description: {channel['description']}\n")
            f.write(f"   Members: {channel.get('member_count', 'unknown')}\n")
            f.write(f"   CONFIG ENTRY: '{channel['username'] or channel['id']}'\n")
            f.write("\n")
        
        f.write("\nGROUPS\n")
        f.write("-" * 80 + "\n")
        for i, group in enumerate(groups, 1):
            f.write(f"{i}. {group['name']} (ID: {group['id']})\n")
            if group['username']:
                f.write(f"   Username: {group['username']}\n")
            f.write(f"   Type: {group['type']}\n")
            f.write(f"   Members: {group.get('participant_count', 'unknown')}\n")
            f.write(f"   CONFIG ENTRY: '{group['username'] or group['id']}'\n")
            f.write("\n")
        
        f.write("\nPRIVATE CHATS (not typically used as sources)\n")
        f.write("-" * 80 + "\n")
        for i, chat in enumerate(private_chats, 1):
            f.write(f"{i}. {chat['name']} (ID: {chat['id']})\n")
            if chat['username']:
                f.write(f"   Username: {chat['username']}\n")
            f.write("\n")
        
        f.write("\nCONFIGURATION EXAMPLES\n")
        f.write("-" * 80 + "\n")
        f.write("# For config.py:\n")
        f.write("SOURCE_CHATS = [\n")
        
        # Add examples of channels
        if channels:
            f.write(f"    '{channels[0]['username'] or channels[0]['id']}',  # {channels[0]['name']} (channel)\n")
        
        # Add examples of groups
        if groups:
            f.write(f"    '{groups[0]['username'] or groups[0]['id']}',  # {groups[0]['name']} (group)\n")
        
        f.write("]\n")
        
        f.write("\n# Forward destination - can be a channel, group, or private chat\n")
        example_id = None
        example_name = None
        
        if channels:
            example_id = channels[0]['id']
            example_name = channels[0]['name']
        elif groups:
            example_id = groups[0]['id']
            example_name = groups[0]['name']
        elif private_chats:
            example_id = private_chats[0]['id']
            example_name = private_chats[0]['name']
        
        if example_id:
            f.write(f"FORWARD_CHAT_ID = {example_id}  # {example_name}\n")
    
    print(f"Chat information saved to {OUTPUT_FILE}")

def write_to_json_file(channels, groups, private_chats):
    """Write chat information to a JSON file for programmatic use."""
    data = {
        "generated_at": datetime.now().isoformat(),
        "channels": channels,
        "groups": groups,
        "private_chats": private_chats
    }
    
    with open(JSON_OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Chat information saved to {JSON_OUTPUT_FILE} (JSON format)")

async def main():
    """Main function."""
    try:
        channels, groups, private_chats = await fetch_chats()
        
        print(f"Found {len(channels)} channels, {len(groups)} groups, and {len(private_chats)} private chats.")
        
        write_to_text_file(channels, groups, private_chats)
        write_to_json_file(channels, groups, private_chats)
        
        print("\nSample entries for config.py:")
        if channels:
            print(f"Channel: '{channels[0]['username'] or channels[0]['id']}'  # {channels[0]['name']}")
        if groups:
            print(f"Group: '{groups[0]['username'] or groups[0]['id']}'  # {groups[0]['name']}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
