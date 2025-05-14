#!/usr/bin/env python3
"""Main entry point for the NFT Scanner application."""

import asyncio
import sys
import os

# Add the current directory to sys.path if it's not already there
# This helps with imports both in development and when deployed in Docker
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from src.nft_scanner.config import Config
from src.nft_scanner.core import NFTScanner
from src.nft_scanner.utils import setup_logger

logger = setup_logger()


async def main():
    """Main entry point for the NFT Scanner."""
    try:
        # Load configuration
        config = Config.from_args()
        config.validate()

        # Initialize scanner
        scanner = NFTScanner(
            bot_token=config.bot_token,
            channel_id=config.channel_id,
            start_id=config.start_id,
            max_nfts=config.max_nfts,
            output_dir=config.output_dir,
            find_latest=config.find_latest,
            monitor=config.monitor,
            check_interval=config.check_interval,
            gift_name=config.gift_name,
            respect_saved=config.respect_saved,
            data_dir=config.data_dir,
        )

        # Run scanner
        await scanner.scan()

    except KeyboardInterrupt:
        logger.info("Scanner stopped by user")
        return 0
    except Exception as e:
        logger.error(f"Error running scanner: {e}")
        logger.exception("Exception details:")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
