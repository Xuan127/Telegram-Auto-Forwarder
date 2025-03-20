"""
Telegram Auto Forwarder - Main entry point.

This script monitors specified Telegram channels and groups for new messages,
filters them using AI, and forwards interesting messages to a target chat.
"""
import asyncio
import signal
import sys
from typing import List, Union

from telethon.tl.types import Channel, Chat, User

from logger import logger, setup_logger
import config
from state_manager import StateManager
from ai_filter import AIFilter
from telegram_client import TelegramForwarder

async def run_forwarder():
    """Run the Telegram Auto Forwarder."""
    # Set up logging
    setup_logger(log_level="INFO")
    
    try:
        # Initialize components
        logger.info("Initializing Telegram Auto Forwarder...")
        state_manager = StateManager()
        ai_filter = AIFilter()
        forwarder = TelegramForwarder(state_manager, ai_filter)
        
        # Start the Telegram client
        await forwarder.start(phone=config.PHONE_NUMBER)
        
        # Set up signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(shutdown(forwarder, state_manager))
            )
        
        # Initialize source chats
        source_entities = []
        for identifier in config.SOURCE_CHATS:
            chat_entity = await forwarder.fetch_chat_entity(identifier)
            if chat_entity:
                await forwarder.initialize_chat(chat_entity)
                source_entities.append(chat_entity)
                chat_type = state_manager.determine_chat_type(chat_entity)
                logger.info(f"Initialized {chat_type} {chat_entity.id} ({getattr(chat_entity, 'title', 'No Title')})")
            else:
                logger.error(f"Could not find chat: {identifier}")
        
        if not source_entities:
            logger.error("No valid source chats found. Exiting.")
            return
            
        # Initialize forward chat (just make sure it exists)
        forward_entity = await forwarder.fetch_chat_entity(config.FORWARD_CHAT_ID)
        if not forward_entity:
            logger.error(f"Could not find forward chat with ID {config.FORWARD_CHAT_ID}. Exiting.")
            return
            
        forward_chat_type = state_manager.determine_chat_type(forward_entity)
        logger.info(f"Using {forward_chat_type} {forward_entity.id} ({getattr(forward_entity, 'title', 'No Title')}) as forward destination")
        
        # Log what we're monitoring
        chat_names = [getattr(entity, 'title', str(entity.id)) for entity in source_entities]
        logger.info(f"Monitoring new messages in: {', '.join(chat_names)}...")
        
        # Main polling loop
        while True:
            for chat_entity in source_entities:
                await forwarder.fetch_new_messages(chat_entity)
            # Wait for a specified interval before polling again
            await asyncio.sleep(config.POLLING_INTERVAL)
            
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        await shutdown(forwarder, state_manager)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        await shutdown(forwarder, state_manager)

async def shutdown(forwarder: TelegramForwarder, state_manager: StateManager):
    """
    Perform graceful shutdown.
    
    Args:
        forwarder: TelegramForwarder instance
        state_manager: StateManager instance
    """
    logger.info("Shutting down...")
    try:
        # Save states one more time on clean exit
        state_manager.save_chat_states()
        state_manager.save_message_hash_store()
        await forwarder.stop()
        logger.info("Bot stopped. Chat states and message hashes saved.")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    finally:
        # Force exit if still running
        sys.exit(0)

if __name__ == '__main__':
    asyncio.run(run_forwarder())
