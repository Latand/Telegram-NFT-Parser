"""State management for persisting NFT scanner state between runs."""

import json
import os
import time

from src.nft_scanner.utils import setup_logger

logger = setup_logger("state-manager")


class StateManager:
    """Manages the persistent state of the NFT scanner."""

    def __init__(self, data_dir: str = "./data", gift_name: str = "SnakeBox"):
        """
        Initialize the state manager.

        Args:
            data_dir: Directory to store state files
            gift_name: Name of the NFT gift collection
        """
        self.data_dir = data_dir
        self.gift_name = gift_name

        # Create data directory if it doesn't exist
        os.makedirs(data_dir, exist_ok=True)

        # Set path for the state file
        self.state_file = os.path.join(
            self.data_dir, f"last_id_{self.gift_name.lower()}.json"
        )

    def load_last_id(self, default_id: int = 0) -> tuple[int, bool]:
        """
        Load the last processed NFT ID from file.

        Args:
            default_id: Default ID to return if no state file exists

        Returns:
            Tuple of (next_id, loaded_successfully)
            next_id: Next ID to process (last_id + 1)
            loaded_successfully: Whether the ID was loaded from file
        """
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    last_id = data.get("last_id")
                    if last_id is not None:
                        next_id = int(last_id) + 1  # Start from the next ID
                        logger.info(
                            f"Loaded last checked NFT ID for {self.gift_name}: {last_id}, starting from {next_id}"
                        )
                        return next_id, True
            except Exception as e:
                logger.error(f"Failed to load last ID from {self.state_file}: {e}")
                # Create a backup of the corrupted file
                if os.path.exists(self.state_file):
                    backup_path = f"{self.state_file}.backup"
                    try:
                        import shutil

                        shutil.copy2(self.state_file, backup_path)
                        logger.info(f"Created backup of corrupted file: {backup_path}")
                    except Exception as e2:
                        logger.error(f"Failed to create backup of corrupted file: {e2}")
        else:
            logger.info(
                f"No saved state file found at {self.state_file}, starting with initial ID"
            )
        return default_id, False

    def save_last_id(self, last_id: int) -> bool:
        """
        Save the last processed NFT ID to file.

        Args:
            last_id: Last ID that was processed

        Returns:
            True if the save was successful, False otherwise
        """
        try:
            # First write to a temporary file, then rename to avoid corruption
            temp_file = f"{self.state_file}.tmp"
            with open(temp_file, "w") as f:
                json.dump({"last_id": last_id, "timestamp": time.time()}, f)

            # Rename the temp file to the actual file (atomic operation on most filesystems)
            os.replace(temp_file, self.state_file)

            logger.info(f"Saved last checked NFT ID for {self.gift_name}: {last_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save last ID to {self.state_file}: {e}")
            return False
