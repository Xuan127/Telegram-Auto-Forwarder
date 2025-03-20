"""
State management for the Telegram Auto Forwarder.
Handles chat states (for both channels and groups) and message hashes.
"""
import json
import os
import hashlib
from typing import Dict, Any, List, Optional, Union
from telethon.tl.patched import Message
from telethon.tl.types import Channel, Chat, User

from logger import logger
import config

class StateManager:
    """Manages persistent state for the Telegram Auto Forwarder."""
    
    def __init__(self):
        """Initialize the state manager."""
        self.chat_states: Dict[int, Dict[str, Any]] = {}
        self.message_hash_store: Dict[str, Any] = {
            "hashes": [""] * config.MESSAGE_HASH_STORE_SIZE,
            "pointer": 0
        }
        
        # Load existing states
        self.load_chat_states()
        self.load_message_hash_store()
    
    def load_chat_states(self) -> None:
        """Load chat states from file if it exists."""
        if not os.path.exists(config.STATE_FILE):
            logger.info(f"State file {config.STATE_FILE} not found. Starting with empty states.")
            return
        
        try:
            with open(config.STATE_FILE, 'r') as f:
                # Convert chat IDs from str back to int
                serialized_states = json.load(f)
                self.chat_states = {int(chat_id): data for chat_id, data in serialized_states.items()}
                logger.info(f"Loaded chat states from {config.STATE_FILE}")
        except Exception as e:
            logger.error(f"Error loading chat states: {e}")
    
    def save_chat_states(self) -> None:
        """Save chat states to a file."""
        # Convert chat IDs from int to str for JSON serialization
        serializable_states = {str(chat_id): data for chat_id, data in self.chat_states.items()}
        try:
            with open(config.STATE_FILE, 'w') as f:
                json.dump(serializable_states, f)
            logger.info(f"Chat states saved to {config.STATE_FILE}")
        except Exception as e:
            logger.error(f"Error saving chat states: {e}")
    
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
    
    def update_chat_state(self, chat_id: int, state_data: Dict[str, Any]) -> None:
        """
        Update the state data for a chat and save the state.
        
        Args:
            chat_id: ID of the chat
            state_data: Dictionary of state data to update
        """
        if chat_id not in self.chat_states:
            self.chat_states[chat_id] = {}
        
        # Update with new state data
        self.chat_states[chat_id].update(state_data)
        self.save_chat_states()
    
    def get_chat_state(self, chat_id: int, key: str) -> Optional[Any]:
        """
        Get a specific state value for a chat if it exists.
        
        Args:
            chat_id: ID of the chat
            key: State key to retrieve
            
        Returns:
            The state value or None if not found
        """
        if chat_id in self.chat_states and key in self.chat_states[chat_id]:
            return self.chat_states[chat_id][key]
        return None
    
    def initialize_chat(self, chat_id: int, chat_type: str, state_data: Dict[str, Any]) -> None:
        """
        Initialize a chat with the given state data.
        
        Args:
            chat_id: ID of the chat
            chat_type: Type of chat ('channel', 'group', or 'private')
            state_data: Initial state data
        """
        self.chat_states[chat_id] = {'type': chat_type, **state_data}
        self.save_chat_states()
        logger.info(f"Initialized {chat_type} {chat_id} with state data: {state_data}")
    
    def get_chat_type(self, chat_id: int) -> Optional[str]:
        """
        Get the type of a chat if it exists.
        
        Args:
            chat_id: ID of the chat
            
        Returns:
            The chat type ('channel', 'group', or 'private') or None if not found
        """
        if chat_id in self.chat_states and 'type' in self.chat_states[chat_id]:
            return self.chat_states[chat_id]['type']
        return None
    
    def determine_chat_type(self, entity: Union[Channel, Chat, User]) -> str:
        """
        Determine the type of chat from a Telegram entity.
        
        Args:
            entity: Telegram entity
            
        Returns:
            Chat type as string ('channel', 'group', or 'private')
        """
        if isinstance(entity, Channel):
            if entity.broadcast:
                return 'channel'
            else:
                return 'group'  # Supergroup
        elif isinstance(entity, Chat):
            return 'group'
        elif isinstance(entity, User):
            return 'private'
        else:
            return 'unknown'
