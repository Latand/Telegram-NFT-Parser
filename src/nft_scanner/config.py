"""Configuration handling for the NFT Scanner."""

import argparse
import os
from dataclasses import dataclass

from environs import Env


@dataclass
class Config:
    """Configuration for the NFT Scanner."""

    # Telegram settings
    bot_token: str
    channel_id: str

    # Scanner settings
    start_id: int = 245
    max_nfts: int = 20
    output_dir: str = "nft_images"
    find_latest: bool = False
    monitor: bool = False
    check_interval: int = 5
    gift_name: str = "SnakeBox"
    respect_saved: bool = False
    data_dir: str = "./data"

    @classmethod
    def from_env(cls) -> "Config":
        """
        Load configuration from environment variables.

        Returns:
            Config object with values loaded from environment
        """
        env = Env()
        env.read_env()  # Read from .env file if it exists

        return cls(
            bot_token=env.str("TELEGRAM_BOT_TOKEN"),
            channel_id=env.str("TELEGRAM_CHANNEL_ID"),
            # Optional environment variables with defaults
            start_id=env.int("NFT_START_ID", 245),
            max_nfts=env.int("NFT_MAX_COUNT", 20),
            output_dir=env.str("NFT_OUTPUT_DIR", "nft_images"),
            find_latest=env.bool("NFT_FIND_LATEST", False),
            monitor=env.bool("NFT_MONITOR", False),
            check_interval=env.int("NFT_CHECK_INTERVAL", 5),
            gift_name=env.str("NFT_GIFT_NAME", "SnakeBox"),
            respect_saved=env.bool("NFT_RESPECT_SAVED", False),
            data_dir=env.str("NFT_DATA_DIR", "./data"),
        )

    @classmethod
    def from_args(cls) -> "Config":
        """
        Parse command line arguments to create configuration.

        Returns:
            Config object with values from command line arguments
        """
        parser = argparse.ArgumentParser(description="Telegram NFT Scanner")
        parser.add_argument("--start", type=int, default=245, help="Starting NFT ID")
        parser.add_argument(
            "--count", type=int, default=20, help="Number of NFTs to find"
        )
        parser.add_argument(
            "--output",
            type=str,
            default="nft_images",
            help="Output directory for NFT images",
        )
        parser.add_argument(
            "--find-latest",
            action="store_true",
            help="Use binary search to quickly find the latest NFT ID before scanning",
        )
        parser.add_argument(
            "--monitor",
            action="store_true",
            help="Continuously monitor for new NFTs after initial scan",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=5,
            help="Interval in seconds between checks when monitoring (default: 5)",
        )
        parser.add_argument(
            "--gift-name",
            type=str,
            default="SnakeBox",
            help="Gift name to track (e.g. SnakeBox, BondedRing)",
        )
        parser.add_argument(
            "--respect-saved",
            action="store_true",
            help="Always respect saved IDs and skip binary search when IDs are loaded from file",
        )
        parser.add_argument(
            "--data-dir",
            type=str,
            default="./data",
            help="Directory to store state files",
        )
        args = parser.parse_args()

        # First load environment variables
        config = cls.from_env()

        # Override with command line arguments
        config.start_id = args.start
        config.max_nfts = args.count
        config.output_dir = args.output
        config.find_latest = args.find_latest
        config.monitor = args.monitor
        config.check_interval = args.interval
        config.gift_name = args.gift_name
        config.respect_saved = args.respect_saved
        config.data_dir = args.data_dir

        # In Docker environments, we always want to respect saved IDs
        # This ensures continuity between container restarts
        if os.path.exists("/app/data"):
            config.respect_saved = True
            print("Docker environment detected, enabling --respect-saved option")

        return config

    def validate(self) -> None:
        """
        Validate the configuration.

        Raises:
            RuntimeError: If any required configuration is missing
        """
        # Check if bot_token is properly configured
        if not self.bot_token:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN is missing in the .env file or environment variables."
            )

        if not self.bot_token.startswith("") or len(self.bot_token) < 20:
            print(
                f"Warning: TELEGRAM_BOT_TOKEN appears to be invalid: {self.bot_token[:5]}..."
            )

        # Check if channel_id is properly configured
        if not self.channel_id:
            raise RuntimeError(
                "TELEGRAM_CHANNEL_ID is missing in the .env file or environment variables."
            )

        # Print configuration summary
        print("\nConfiguration:")
        print(f"  Telegram Channel ID: {self.channel_id}")
        print(f"  Bot Token: {self.bot_token[:5]}... (hidden)")
        print(f"  Gift Name: {self.gift_name}")
        print(f"  Start ID: {self.start_id}")
        print(f"  Monitor Mode: {self.monitor}")
        print(f"  Output Directory: {self.output_dir}")
        print(f"  Data Directory: {self.data_dir}")
        print(f"  Find Latest: {self.find_latest}")
        print(f"  Respect Saved: {self.respect_saved}")
        print("")
