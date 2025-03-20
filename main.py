"""
Telegram Auto Forwarder - Main entry point.

This script monitors specified Telegram channels for new messages,
filters them using AI, and forwards interesting messages to a target channel.
"""
import asyncio
import signal
import sys
from typing import List

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
        
        # Initialize channels
        source_channels = []
        for username in config.SOURCE_CHANNELS:
            channel = await forwarder.fetch_channel_entity(username)
            if channel:
                await forwarder.initialize_channel(channel)
                source_channels.append(channel)
            else:
                logger.error(f"Could not find channel: {username}")
        
        if not source_channels:
            logger.error("No valid source channels found. Exiting.")
            return
        
        logger.info(f"Monitoring new messages in channels: {', '.join(config.SOURCE_CHANNELS)}...")
        
        # Main polling loop
        while True:
            for channel in source_channels:
                await forwarder.fetch_channel_difference(channel)
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
        state_manager.save_channel_states()
        state_manager.save_message_hash_store()
        await forwarder.stop()
        logger.info("Bot stopped. Channel states and message hashes saved.")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    finally:
        # Force exit if still running
        sys.exit(0)

if __name__ == '__main__':
    asyncio.run(run_forwarder())
