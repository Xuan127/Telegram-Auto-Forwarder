"""
Telegram client functionality for the Telegram Auto Forwarder.
"""
import asyncio
from typing import Dict, List, Optional, Tuple, Set
from telethon import TelegramClient, functions, types
from telethon.tl.patched import Message
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
    
    async def fetch_channel_entity(self, username: str) -> Optional[types.Channel]:
        """
        Fetch a channel entity by username.
        
        Args:
            username: Channel username
            
        Returns:
            Channel entity or None if not found
        """
        try:
            return await self.client.get_entity(username)
        except Exception as e:
            logger.error(f"Failed to get entity for {username}: {e}")
            return None
    
    async def initialize_channel(self, channel) -> None:
        """
        Initialize a channel's state if not already initialized.
        
        Args:
            channel: Channel entity
        """
        # If we already have state for this channel, use it
        if self.state_manager.get_channel_pts(channel.id) is not None:
            logger.info(f"Using saved state for channel {channel.id} with pts {self.state_manager.get_channel_pts(channel.id)}")
            return
            
        # Otherwise initialize with the proper pts using GetChannelRequest
        try:
            full_channel = await self.client(functions.channels.GetFullChannelRequest(
                channel=channel
            ))
            
            # Initialize with the proper pts from the full channel info
            pts = full_channel.full_chat.pts
            self.state_manager.initialize_channel(channel.id, pts)
        except Exception as e:
            logger.error(f"Failed to initialize channel {channel.id}: {e}")
    
    async def fetch_channel_difference(self, channel) -> None:
        """
        Fetch new messages from a channel.
        
        Args:
            channel: Channel entity
        """
        try:
            pts = self.state_manager.get_channel_pts(channel.id)
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
            self.state_manager.update_channel_pts(channel.id, result.pts)
            
        except FloodWaitError as e:
            logger.warning(f"Rate limited. Waiting for {e.seconds} seconds.")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"An error occurred while fetching updates from channel {channel.id}: {e}")
    
    async def process_new_message(self, channel, message: Message) -> None:
        """
        Process a new message from a channel.
        
        Args:
            channel: Source channel entity
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
                    asyncio.create_task(self.process_group_after_delay(channel, group_id))
            else:
                # Regular non-grouped message
                message_content = message.message or ""
                if self.ai_filter.is_content_interesting(message_content):
                    forward_channel_entity = await self.client.get_entity(config.FORWARD_CHANNEL_ID)
                    await self.client.forward_messages(forward_channel_entity, message, channel)
                    # Add hash to store after successful forwarding
                    self.state_manager.add_hash_to_store(message_hash)
                    logger.info(f"Forwarded regular message {message.id} to {forward_channel_entity.title}")
                else:
                    logger.info(f"Message {message.id} filtered out as not interesting")
        except Exception as e:
            logger.error(f"Failed to process message {message.id}: {e}")
    
    async def process_group_after_delay(self, channel, group_id: int, delay_seconds: int = None) -> None:
        """
        Process a group of messages after collecting them for a short time.
        
        Args:
            channel: Source channel entity
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
                forward_channel_entity = await self.client.get_entity(config.FORWARD_CHANNEL_ID)
                for message, message_hash in message_tuples:
                    await self.client.forward_messages(forward_channel_entity, message, channel)
                    # Add hash to store after successful forwarding
                    self.state_manager.add_hash_to_store(message_hash)
                    logger.info(f"Forwarded grouped message {message.id} to {forward_channel_entity.title}")
            elif group_already_processed:
                logger.debug(f"Media group {group_id} already processed (hash in store). Skipping.")
            else:
                logger.info(f"Media group {group_id} filtered out as not interesting")
        except Exception as e:
            logger.error(f"Error processing message group {group_id}: {e}")
            if group_id in self.processing_groups:
                self.processing_groups.remove(group_id)
