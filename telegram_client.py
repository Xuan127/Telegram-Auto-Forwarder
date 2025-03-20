"""
Telegram client functionality for the Telegram Auto Forwarder.
Supports both channels and groups.
"""
import asyncio
from typing import Dict, List, Optional, Tuple, Set, Union, Any
from telethon import TelegramClient, functions, types
from telethon.tl.patched import Message
from telethon.tl.types import Channel, Chat, User, InputChannel, InputPeerChannel, InputPeerChat, InputPeerUser
from telethon.errors import FloodWaitError

from logger import logger
import config
from state_manager import StateManager
from ai_filter import AIFilter

class TelegramForwarder:
    """Handles Telegram client operations for message forwarding."""
    
    def __init__(self, state_manager: StateManager, ai_filter: AIFilter):
        """
        Initialize the Telegram forwarder.
        
        Args:
            state_manager: StateManager instance for handling state
            ai_filter: AIFilter instance for filtering messages
        """
        self.client = TelegramClient(
            config.SESSION_NAME,
            config.API_ID,
            config.API_HASH
        )
        self.state_manager = state_manager
        self.ai_filter = ai_filter
        
        # Dictionary to store grouped messages until all are received
        self.grouped_messages: Dict[int, List[Tuple[Message, str]]] = {}
        self.processing_groups: Set[int] = set()
        
        # Store chat entities to avoid repeated lookups
        self.chat_entities: Dict[int, Any] = {}
    
    async def start(self, phone: str) -> None:
        """
        Start the Telegram client.
        
        Args:
            phone: Phone number for authentication
        """
        await self.client.start(phone=phone)
        logger.info("Telegram client started successfully")
    
    async def stop(self) -> None:
        """Stop the Telegram client."""
        await self.client.disconnect()
        logger.info("Telegram client stopped")
    
    async def fetch_chat_entity(self, identifier: Union[str, int]) -> Optional[Union[Channel, Chat, User]]:
        """
        Fetch a chat entity by username or ID.
        
        Args:
            identifier: Chat username or ID
            
        Returns:
            Chat entity or None if not found
        """
        try:
            entity = await self.client.get_entity(identifier)
            # Cache the entity
            self.chat_entities[entity.id] = entity
            return entity
        except Exception as e:
            logger.error(f"Failed to get entity for {identifier}: {e}")
            return None
    
    async def initialize_chat(self, chat_entity: Union[Channel, Chat, User]) -> None:
        """
        Initialize a chat's state if not already initialized.
        
        Args:
            chat_entity: Chat entity
        """
        chat_id = chat_entity.id
        chat_type = self.state_manager.determine_chat_type(chat_entity)
        
        # If we already have state for this chat, use it
        if self.state_manager.get_chat_type(chat_id) is not None:
            logger.info(f"Using saved state for {chat_type} {chat_id}")
            return
            
        # Initialize with appropriate state data based on chat type
        if chat_type == 'channel':
            # For channels, we need the PTS value
            try:
                full_channel = await self.client(functions.channels.GetFullChannelRequest(
                    channel=chat_entity
                ))
                pts = full_channel.full_chat.pts
                self.state_manager.initialize_chat(chat_id, chat_type, {'pts': pts})
            except Exception as e:
                logger.error(f"Failed to initialize channel {chat_id}: {e}")
        elif chat_type == 'group':
            # For groups, we'll track the last message ID
            try:
                # Get the most recent message to start tracking from
                messages = await self.client.get_messages(chat_entity, limit=1)
                last_id = messages[0].id if messages else 0
                self.state_manager.initialize_chat(chat_id, chat_type, {'last_id': last_id})
            except Exception as e:
                logger.error(f"Failed to initialize group {chat_id}: {e}")
        else:
            # For other chat types, just initialize with empty state
            self.state_manager.initialize_chat(chat_id, chat_type, {})
    
    async def fetch_new_messages(self, chat_entity: Union[Channel, Chat, User]) -> None:
        """
        Fetch new messages from a chat.
        
        Args:
            chat_entity: Chat entity
        """
        chat_id = chat_entity.id
        chat_type = self.state_manager.get_chat_type(chat_id)
        
        if chat_type == 'channel':
            await self._fetch_channel_difference(chat_entity)
        elif chat_type == 'group':
            await self._fetch_group_messages(chat_entity)
        else:
            logger.warning(f"Unsupported chat type: {chat_type} for chat {chat_id}")
    
    async def _fetch_channel_difference(self, channel: Channel) -> None:
        """
        Fetch new messages from a channel using GetChannelDifferenceRequest.
        
        Args:
            channel: Channel entity
        """
        try:
            pts = self.state_manager.get_chat_state(channel.id, 'pts')
            if pts is None:
                logger.error(f"No PTS found for channel {channel.id}")
                return
                
            result = await self.client(functions.updates.GetChannelDifferenceRequest(
                channel=types.InputChannel(channel.id, channel.access_hash),
                filter=types.ChannelMessagesFilterEmpty(),
                pts=pts,
                limit=100,
                force=True
            ))

            # Check the type of result to handle different response types
            if hasattr(result, 'new_messages'):
                # Process new messages
                for message in result.new_messages:
                    await self.process_new_message(channel, message)

            # Update the state variables - pts should be available in all response types
            self.state_manager.update_chat_state(channel.id, {'pts': result.pts})
            
        except FloodWaitError as e:
            logger.warning(f"Rate limited. Waiting for {e.seconds} seconds.")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"An error occurred while fetching updates from channel {channel.id}: {e}")
    
    async def _fetch_group_messages(self, group: Union[Chat, Channel]) -> None:
        """
        Fetch new messages from a group using get_messages.
        
        Args:
            group: Group entity (can be a regular group or a supergroup)
        """
        try:
            last_id = self.state_manager.get_chat_state(group.id, 'last_id') or 0
            
            # Get messages newer than the last processed ID
            messages = await self.client.get_messages(
                group,
                limit=100,  # Adjust as needed
                min_id=last_id
            )
            
            if not messages:
                return
                
            # Process messages in chronological order (oldest first)
            for message in reversed(messages):
                await self.process_new_message(group, message)
                
            # Update the last message ID
            new_last_id = max(msg.id for msg in messages)
            self.state_manager.update_chat_state(group.id, {'last_id': new_last_id})
            
        except FloodWaitError as e:
            logger.warning(f"Rate limited. Waiting for {e.seconds} seconds.")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"An error occurred while fetching messages from group {group.id}: {e}")
    
    async def process_new_message(self, chat_entity: Union[Channel, Chat, User], message: Message) -> None:
        """
        Process a new message from a chat.
        
        Args:
            chat_entity: Source chat entity
            message: Message to process
        """
        try:
            # Generate hash for this message
            message_hash = self.state_manager.generate_message_hash(message)
            
            # Check if we've already processed this message
            if self.state_manager.is_hash_in_store(message_hash):
                logger.debug(f"Message {message.id} already processed (hash in store). Skipping.")
                return
                
            if message.grouped_id:
                # This message is part of a media group/album
                group_id = message.grouped_id
                
                if group_id not in self.grouped_messages:
                    self.grouped_messages[group_id] = []
                    
                self.grouped_messages[group_id].append((message, message_hash))
                
                # Start a task to process this group after a delay (to collect all messages)
                if group_id not in self.processing_groups:
                    self.processing_groups.add(group_id)
                    asyncio.create_task(self.process_group_after_delay(chat_entity, group_id))
            else:
                # Regular non-grouped message
                message_content = message.message or ""
                if self.ai_filter.is_content_interesting(message_content):
                    forward_chat_entity = await self.fetch_chat_entity(config.FORWARD_CHAT_ID)
                    if forward_chat_entity:
                        await self.client.forward_messages(forward_chat_entity, message, chat_entity)
                        # Add hash to store after successful forwarding
                        self.state_manager.add_hash_to_store(message_hash)
                        logger.info(f"Forwarded message {message.id} from {chat_entity.id} to {forward_chat_entity.id}")
                    else:
                        logger.error(f"Could not find forward chat with ID {config.FORWARD_CHAT_ID}")
                else:
                    logger.info(f"Message {message.id} filtered out as not interesting")
        except Exception as e:
            logger.error(f"Failed to process message {message.id}: {e}")
    
    async def process_group_after_delay(self, chat_entity: Union[Channel, Chat, User], group_id: int, delay_seconds: int = None) -> None:
        """
        Process a group of messages after collecting them for a short time.
        
        Args:
            chat_entity: Source chat entity
            group_id: Group ID of the messages
            delay_seconds: Delay in seconds before processing (defaults to config value)
        """
        if delay_seconds is None:
            delay_seconds = config.GROUP_PROCESSING_DELAY
            
        await asyncio.sleep(delay_seconds)  # Wait to collect all messages in group
        
        try:
            if group_id not in self.grouped_messages:
                return
                
            message_tuples = self.grouped_messages[group_id]
            del self.grouped_messages[group_id]
            self.processing_groups.remove(group_id)
            
            # Extract content from all messages in the group
            messages_content = ""
            for msg, _ in message_tuples:
                if hasattr(msg, 'message') and msg.message:
                    messages_content += msg.message + " "
                elif hasattr(msg, 'caption') and msg.caption:
                    messages_content += msg.caption + " "
            
            logger.debug(f"Processing group with {len(message_tuples)} messages. Content: {messages_content.strip()[:100]}...")
            
            # Check if any message in the group is already in hash store
            group_already_processed = any(self.state_manager.is_hash_in_store(msg_hash) for _, msg_hash in message_tuples)
            
            if not group_already_processed and self.ai_filter.is_content_interesting(messages_content):
                forward_chat_entity = await self.fetch_chat_entity(config.FORWARD_CHAT_ID)
                if forward_chat_entity:
                    for message, message_hash in message_tuples:
                        await self.client.forward_messages(forward_chat_entity, message, chat_entity)
                        # Add hash to store after successful forwarding
                        self.state_manager.add_hash_to_store(message_hash)
                        logger.info(f"Forwarded grouped message {message.id} to {forward_chat_entity.id}")
                else:
                    logger.error(f"Could not find forward chat with ID {config.FORWARD_CHAT_ID}")
            elif group_already_processed:
                logger.debug(f"Media group {group_id} already processed (hash in store). Skipping.")
            else:
                logger.info(f"Media group {group_id} filtered out as not interesting")
        except Exception as e:
            logger.error(f"Error processing message group {group_id}: {e}")
            if group_id in self.processing_groups:
                self.processing_groups.remove(group_id)
