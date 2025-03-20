"""
State management for the Telegram Auto Forwarder.
Handles channel states and message hashes.
"""
import json
import os
import hashlib
from typing import Dict, Any, List, Optional
from telethon.tl.patched import Message

from logger import logger
import config

class StateManager:
    """Manages persistent state for the Telegram Auto Forwarder."""
    
    def __init__(self):
        """Initialize the state manager."""
        self.channel_states: Dict[int, Dict[str, Any]] = {}
        self.message_hash_store: Dict[str, Any] = {
            "hashes": [""] * config.MESSAGE_HASH_STORE_SIZE,
            "pointer": 0
        }
        
        # Load existing states
        self.load_channel_states()
        self.load_message_hash_store()
    
    def load_channel_states(self) -> None:
        """Load channel states from file if it exists."""
        if not os.path.exists(config.STATE_FILE):
            logger.info(f"State file {config.STATE_FILE} not found. Starting with empty states.")
            return
        
        try:
            with open(config.STATE_FILE, 'r') as f:
                # Convert channel IDs from str back to int
                serialized_states = json.load(f)
                self.channel_states = {int(channel_id): data for channel_id, data in serialized_states.items()}
                logger.info(f"Loaded channel states from {config.STATE_FILE}")
        except Exception as e:
            logger.error(f"Error loading channel states: {e}")
    
    def save_channel_states(self) -> None:
        """Save channel states to a file."""
        # Convert channel IDs from int to str for JSON serialization
        serializable_states = {str(channel_id): data for channel_id, data in self.channel_states.items()}
        try:
            with open(config.STATE_FILE, 'w') as f:
                json.dump(serializable_states, f)
            logger.info(f"Channel states saved to {config.STATE_FILE}")
        except Exception as e:
            logger.error(f"Error saving channel states: {e}")
    
    def load_message_hash_store(self) -> None:
        """Load message hash store from file or initialize if not exists."""
        if os.path.exists(config.MESSAGE_HASH_FILE):
            try:
                with open(config.MESSAGE_HASH_FILE, 'r') as f:
                    self.message_hash_store = json.load(f)
                    logger.info(f"Loaded message hash store from {config.MESSAGE_HASH_FILE}")
            except Exception as e:
                logger.error(f"Error loading message hash store: {e}")
                # Initialize with default values if loading fails
                self.message_hash_store = {
                    "hashes": [""] * config.MESSAGE_HASH_STORE_SIZE,
                    "pointer": 0
                }
        else:
            # Initialize with default values if file doesn't exist
            self.message_hash_store = {
                "hashes": [""] * config.MESSAGE_HASH_STORE_SIZE,
                "pointer": 0
            }
            self.save_message_hash_store()
    
    def save_message_hash_store(self) -> None:
        """Save message hash store to file."""
        try:
            with open(config.MESSAGE_HASH_FILE, 'w') as f:
                json.dump(self.message_hash_store, f)
            logger.info(f"Message hash store saved to {config.MESSAGE_HASH_FILE}")
        except Exception as e:
            logger.error(f"Error saving message hash store: {e}")
    
    def is_hash_in_store(self, message_hash: str) -> bool:
        """Check if a message hash exists in the store."""
        return message_hash in self.message_hash_store["hashes"]
    
    def add_hash_to_store(self, message_hash: str) -> None:
        """Add a new hash to the store and update the pointer."""
        pointer = self.message_hash_store["pointer"]
        self.message_hash_store["hashes"][pointer] = message_hash
        # Update pointer (circular buffer)
        self.message_hash_store["pointer"] = (pointer + 1) % config.MESSAGE_HASH_STORE_SIZE
        self.save_message_hash_store()
    
    def generate_message_hash(self, message: Message) -> str:
        """Generate a hash for a message using only message.message content."""
        content = message.message if message.message else ""
        return hashlib.sha256(content.encode()).hexdigest()
    
    def update_channel_pts(self, channel_id: int, pts: int) -> None:
        """Update the PTS value for a channel and save the state."""
        if channel_id not in self.channel_states:
            self.channel_states[channel_id] = {}
        
        self.channel_states[channel_id]['pts'] = pts
        self.save_channel_states()
    
    def get_channel_pts(self, channel_id: int) -> Optional[int]:
        """Get the PTS value for a channel if it exists."""
        if channel_id in self.channel_states and 'pts' in self.channel_states[channel_id]:
            return self.channel_states[channel_id]['pts']
        return None
    
    def initialize_channel(self, channel_id: int, pts: int) -> None:
        """Initialize a channel with the given PTS value."""
        self.channel_states[channel_id] = {'pts': pts}
        self.save_channel_states()
        logger.info(f"Initialized channel {channel_id} with pts {pts}")
