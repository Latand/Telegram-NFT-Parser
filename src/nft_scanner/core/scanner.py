"""Core NFT scanner implementation."""

import os
import asyncio
import time
from collections import deque
from typing import Optional

from aiohttp import ClientSession, ClientTimeout

from src.nft_scanner.models import NFT
from src.nft_scanner.utils import setup_logger, parse_nft_page, ImageHandler
from src.nft_scanner.clients import TelegramClient
from src.nft_scanner.storage import StateManager


logger = setup_logger("nft-scanner")


class NFTScanner:
    """Main scanner class for finding and downloading NFTs."""

    def __init__(
        self,
        bot_token: str,
        channel_id: str,
        start_id: int = 245,
        max_nfts: int = 20,
        output_dir: str = "nft_images",
        find_latest: bool = False,
        monitor: bool = False,
        check_interval: int = 5,
        gift_name: str = "SnakeBox",
        respect_saved: bool = False,
        data_dir: str = "./data",
    ):
        """
        Initialize the NFT scanner.

        Args:
            bot_token: Telegram bot token
            channel_id: Telegram channel ID to send notifications to
            start_id: ID to start scanning from
            max_nfts: Maximum number of NFTs to find
            output_dir: Directory to save NFT images to
            find_latest: Whether to use binary search to find the latest NFT ID
            monitor: Whether to continuously monitor for new NFTs
            check_interval: Interval in seconds between checks when monitoring
            gift_name: Name of the NFT gift collection
            respect_saved: Whether to respect saved IDs when find_latest is enabled
            data_dir: Directory to store state files
        """
        self.start_id = start_id
        self.current_id = start_id
        self.max_nfts = max_nfts
        self.output_dir = output_dir
        self.gift_name = gift_name
        self.base_url = "https://t.me/nft/"
        self.found_nfts = deque(maxlen=max_nfts)
        self.find_latest = find_latest
        self.monitor = monitor
        self.check_interval = check_interval
        self.timeout = ClientTimeout(total=5)  # 5 second timeout for requests
        self.respect_saved = respect_saved

        # Create components
        self.telegram = TelegramClient(bot_token, channel_id)
        self.state_manager = StateManager(data_dir, gift_name)
        self.image_handler = ImageHandler(output_dir)

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Load last ID from state
        self._loaded_from_file = False
        self._load_last_id()

        # Respect the start_id argument by taking the maximum of saved ID and start_id
        if self.current_id < self.start_id:
            logger.info(
                f"Saved ID {self.current_id} is less than start_id {self.start_id}, using start_id"
            )
            self.current_id = self.start_id
            self._loaded_from_file = (
                False  # Reset flag since we're using start_id instead
            )

        logger.info(
            f"Initialized scanner for {self.gift_name} with ID: {self.current_id}"
        )

    def _load_last_id(self):
        """Load the last processed NFT ID from file."""
        next_id, loaded = self.state_manager.load_last_id(self.current_id)
        self.current_id = next_id
        self._loaded_from_file = loaded

    def _save_last_id(self, last_id: int):
        """Save the last processed NFT ID to file."""
        self.state_manager.save_last_id(last_id)

    async def find_latest_nft_id(self, session: ClientSession) -> int:
        """
        Use a binary search-like approach to quickly find the latest NFT ID.

        Args:
            session: ClientSession to use for requests

        Returns:
            Latest NFT ID
        """
        logger.info("Finding the latest NFT ID using accelerated search...")

        # Start with small steps first since NFT IDs might not be very high
        initial_steps = [100, 500, 1000]
        current_id = self.start_id
        last_valid_id = None  # Initialize with None

        # First phase: gradually increase ID with conservative step sizes
        for step in initial_steps:
            found_upper_bound = False
            for _ in range(5):  # Try at most 5 jumps per step size
                test_id = current_id + step
                exists = await self._nft_exists_with_content_check(test_id, session)

                if exists:
                    logger.info(f"ID {test_id} exists, jumping by {step}")
                    current_id = test_id
                    last_valid_id = test_id
                else:
                    logger.info(
                        f"ID {test_id} doesn't exist, found upper bound with step {step}"
                    )
                    found_upper_bound = True
                    break

            if found_upper_bound:
                break

        # If we didn't find any valid ID in the first phase, check if the start_id is valid
        if last_valid_id is None:
            exists = await self._nft_exists_with_content_check(current_id, session)
            if exists:
                last_valid_id = current_id
            else:
                # No valid IDs found
                logger.warning(f"No valid NFTs found starting from ID {self.start_id}")
                return self.start_id

        # Second phase: binary search between last valid and first invalid
        upper_bound = current_id + step  # The first ID we know doesn't exist
        lower_bound = last_valid_id  # The last ID we know exists

        logger.info(f"Starting binary search between {lower_bound} and {upper_bound}")

        while upper_bound - lower_bound > 1:
            mid = lower_bound + (upper_bound - lower_bound) // 2
            logger.info(f"Testing ID {mid} (range {lower_bound}-{upper_bound})")

            exists = await self._nft_exists_with_content_check(mid, session)
            if exists:
                logger.info(f"ID {mid} exists, adjusting lower bound")
                lower_bound = mid
            else:
                logger.info(f"ID {mid} doesn't exist, adjusting upper bound")
                upper_bound = mid

        latest_id = lower_bound
        logger.info(f"Found latest NFT ID: {latest_id}")

        # Verify this ID actually exists one more time
        final_check = await self.check_nft(latest_id, session)
        if not final_check:
            logger.warning(
                f"Binary search found ID {latest_id}, but final verification failed"
            )
            # Search backwards for a valid ID
            for i in range(5):  # Try up to 5 IDs back
                test_id = latest_id - i - 1
                if test_id < 1:
                    break
                test_result = await self.check_nft(test_id, session)
                if test_result:
                    logger.info(f"Found valid ID {test_id} during fallback check")
                    return test_id
            # If all else fails, return start_id
            return self.start_id

        return latest_id

    async def _nft_exists(self, nft_id: int, session: ClientSession) -> bool:
        """
        Check if an NFT with the given ID exists based on HTTP status.

        Args:
            nft_id: ID to check
            session: ClientSession to use for request

        Returns:
            True if NFT exists, False otherwise
        """
        url = f"{self.base_url}{self.gift_name}-{nft_id}"
        try:
            async with session.get(url, timeout=self.timeout) as response:
                return response.status == 200
        except asyncio.TimeoutError:
            logger.warning(f"Request for ID {nft_id} timed out")
            return False
        except Exception as e:
            logger.warning(f"Error checking NFT {nft_id}: {e}")
            return False

    async def _nft_exists_with_content_check(
        self, nft_id: int, session: ClientSession
    ) -> bool:
        """
        Check if an NFT with the given ID exists by examining page content.

        Args:
            nft_id: ID to check
            session: ClientSession to use for request

        Returns:
            True if NFT exists and has valid content, False otherwise
        """
        url = f"{self.base_url}{self.gift_name}-{nft_id}"
        try:
            async with session.get(url, timeout=self.timeout) as response:
                if response.status != 200:
                    return False

                # Check content to verify it's a valid NFT page
                html = await response.text()
                nft = parse_nft_page(html, nft_id, self.gift_name)
                return nft is not None

        except asyncio.TimeoutError:
            logger.warning(f"Request for ID {nft_id} timed out")
            return False
        except Exception as e:
            logger.warning(f"Error checking NFT {nft_id}: {e}")
            return False

    async def check_nft(self, nft_id: int, session: ClientSession) -> Optional[NFT]:
        """
        Check if NFT with given ID exists and extract its data.

        Args:
            nft_id: ID to check
            session: ClientSession to use for request

        Returns:
            NFT object if found, None otherwise
        """
        url = f"{self.base_url}{self.gift_name}-{nft_id}"
        try:
            async with session.get(url, timeout=self.timeout) as response:
                if response.status != 200:
                    return None

                html = await response.text()
                return parse_nft_page(html, nft_id, self.gift_name)

        except Exception as e:
            logger.error(f"Error checking NFT {nft_id}: {e}")
            return None

    async def download_nft_image(self, nft: NFT, session: ClientSession) -> bool:
        """
        Download NFT image and save it to the output directory.

        Args:
            nft: NFT to download image for
            session: ClientSession to use for downloading

        Returns:
            True if download was successful, False otherwise
        """
        return await self.image_handler.download_image(nft, session) is not None

    async def scan(self):
        """
        Main scanning function to find and download the latest NFTs.

        Returns:
            List of found NFTs
        """
        async with ClientSession(timeout=self.timeout) as session:
            # If enabled, find the latest NFT ID, but only if we don't have a recent saved ID
            should_skip_search = self._loaded_from_file and self.respect_saved

            if self.find_latest and not should_skip_search:
                # We'll only run the latest check if find_latest is enabled AND we either
                # 1. Didn't load from file, or
                # 2. Are explicitly ignoring saved files (respect_saved=False)
                logger.info(
                    f"Finding latest NFT ID starting from current ID: {self.current_id}"
                )
                latest_id = await self.find_latest_nft_id(session)

                # Double-check that this ID is valid before proceeding
                latest_nft = await self.check_nft(latest_id, session)
                if not latest_nft:
                    logger.warning(
                        f"Found latest ID {latest_id} but verification failed, falling back to current ID {self.current_id}"
                    )
                    latest_id = self.current_id

                # Calculate how many NFTs back we need to go to get max_nfts
                # but never go below our current ID
                start_id = max(self.current_id, latest_id - self.max_nfts + 1)
                self.current_id = start_id
                logger.info(
                    f"Latest NFT ID: {latest_id}. Starting scan from ID {start_id} to get up to {self.max_nfts} latest NFTs"
                )
            elif should_skip_search:
                logger.info(
                    f"Using saved ID from file: {self.current_id - 1}, skipping binary search and starting scan from {self.current_id}"
                )

            # Main scanning loop
            valid_results = 0
            consecutive_empty = 0
            max_consecutive_empty = (
                10  # Stop scanning after this many consecutive misses
            )

            # Collect all found NFTs during this scan
            newly_found_nfts = []

            while (
                valid_results < self.max_nfts
                and consecutive_empty < max_consecutive_empty
            ):
                logger.info(f"Checking NFT ID: {self.current_id}")

                nft = await self.check_nft(self.current_id, session)

                if nft:
                    logger.info(f"Found NFT: {nft.name} {nft.full_id}")
                    self.found_nfts.append(nft)
                    newly_found_nfts.append(nft)
                    await self.download_nft_image(nft, session)
                    valid_results += 1
                    consecutive_empty = 0  # Reset counter on successful find
                else:
                    consecutive_empty += 1
                    if consecutive_empty >= max_consecutive_empty:
                        logger.info(
                            f"Reached {max_consecutive_empty} consecutive NFTs not found, stopping scan"
                        )
                        break

                self.current_id += 1
                await asyncio.sleep(1)  # Wait 1 second between requests

            # Save the last checked ID for continuity
            if valid_results > 0:
                # Find the highest ID we got
                highest_id = max(nft.id for nft in self.found_nfts)
                self._save_last_id(highest_id)

                # Send notifications for all newly found NFTs
                if newly_found_nfts:
                    logger.info(
                        f"Sending notifications for {len(newly_found_nfts)} newly found NFTs"
                    )
                    # Send a batch notification about all found NFTs
                    await self.telegram.send_batch_notification(newly_found_nfts)

                    # Also send TGS stickers if any match criteria
                    await self.telegram.send_tgs_stickers(newly_found_nfts)

            self.print_summary()

            # If monitoring mode is enabled, start continuous monitoring
            if self.monitor:
                await self.monitor_new_nfts(session)

            return list(self.found_nfts)

    async def monitor_new_nfts(self, session: ClientSession):
        """
        Continuously monitor for new NFTs beyond the latest known ID.

        Args:
            session: ClientSession to use for requests
        """
        if self.found_nfts:
            highest_id = max(nft.id for nft in self.found_nfts)
            next_id = highest_id + 1
        else:
            next_id = self.current_id

        logger.info(f"Starting continuous monitoring for new NFTs from ID {next_id}")
        logger.info("Will poll for up to 10 seconds. Press Ctrl+C to stop.")

        try:
            while True:
                batch_nfts = []
                poll_start = next_id
                poll_current = poll_start
                found_gap = False
                consecutive_not_found = 0
                max_consecutive_not_found = 5  # Stop after 5 consecutive NFTs not found

                # Try to find NFTs for up to 10 seconds
                poll_start_time = time.time()
                poll_deadline = poll_start_time + 10  # Check for up to 10 seconds

                # Keep checking until either:
                # 1. We hit 5 consecutive not found
                # 2. 10 seconds have passed
                while (
                    time.time() < poll_deadline
                    and consecutive_not_found < max_consecutive_not_found
                ):
                    nft = await self.check_nft(poll_current, session)
                    if nft:
                        logger.info(
                            f"New NFT found and added to batch: {nft.name} {nft.full_id} (ID: {nft.id})"
                        )
                        self.found_nfts.append(nft)
                        batch_nfts.append(nft)
                        poll_current += 1
                        consecutive_not_found = 0  # Reset counter on successful find
                    else:
                        consecutive_not_found += 1
                        if consecutive_not_found >= max_consecutive_not_found:
                            logger.info(
                                f"Reached {max_consecutive_not_found} consecutive NFTs not found, stopping search"
                            )
                            found_gap = True
                            break
                        logger.info(
                            f"NFT ID {poll_current} not found, checking next ID"
                        )
                        poll_current += 1
                        await asyncio.sleep(0.5)

                elapsed_time = time.time() - poll_start_time
                logger.info(
                    f"Polling completed in {elapsed_time:.2f} seconds, found {len(batch_nfts)} NFTs"
                )

                # Only update next_id if we found at least one NFT
                if batch_nfts:
                    # Update next_id to the ID after the last found NFT
                    next_id = max(nft.id for nft in batch_nfts) + 1
                    logger.info(f"Updated next ID to {next_id} for next polling cycle")

                    # Save the highest ID we've found
                    self._save_last_id(next_id - 1)

                    # Send notification about all found NFTs
                    # The send_batch_notification method will handle single NFTs specially
                    await self.telegram.send_batch_notification(batch_nfts)

                    # Also alert in the console if running locally
                    if len(batch_nfts) == 1:
                        self.alert_new_nft(batch_nfts[0])

                    # Send special notifications for TGS stickers with specific model and rarity
                    await self.telegram.send_tgs_stickers(batch_nfts)
                elif found_gap:
                    # If we hit a gap (consecutive not found), stay at the current position
                    logger.info(
                        f"No new NFTs found in this polling period. Staying at ID {next_id}"
                    )
                else:
                    # If we timed out without finding NFTs or gaps, increment by 1 to avoid getting stuck
                    next_id += 1
                    logger.info(
                        f"Timeout without finding NFTs. Moving to next ID {next_id}"
                    )

                # If no NFTs found, sleep for a longer period to avoid hammering the server
                if not batch_nfts:
                    logger.info(
                        "No new NFTs found in this polling period. Waiting 5 seconds..."
                    )
                    await asyncio.sleep(5)  # Rest longer when no NFTs are found

        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user.")
        except Exception as e:
            logger.error(f"Error during monitoring: {e}")
            logger.exception("Full exception details:")

    def print_summary(self):
        """Print a summary of the found NFTs."""
        print("\n===== NFT SCANNER SUMMARY =====")
        print(f"Found {len(self.found_nfts)} NFTs:")
        for i, nft in enumerate(self.found_nfts, 1):
            print(f"\n{i}. {nft.name} {nft.full_id}")

            # Print rarity information if available
            if nft.rarity:
                for prop, info in nft.rarity.items():
                    rarity_str = f" ({info['rarity']})" if info["rarity"] else ""
                    print(f"   - {prop}: {info['value']}{rarity_str}")

        print(f"\nImages saved to: {os.path.abspath(self.output_dir)}")
        print("==============================\n")

    def alert_new_nft(self, nft: NFT):
        """
        Make a sound and visual alert when a new NFT is found.

        Args:
            nft: NFT to alert about
        """
        # Make a terminal beep sound (ASCII bell character)
        print("\a", flush=True)

        # For more visibility, print a special message with multiple beeps
        for _ in range(3):
            print("\a", end="", flush=True)
            time.sleep(0.3)

        # Display appropriate emoji based on rarity
        if nft.is_super_rare:
            rarity_emoji = "🔥🔥🔥 SUPER RARE 🔥🔥🔥"
        elif nft.is_rare:
            rarity_emoji = "🔥 RARE 🔥"
        else:
            rarity_emoji = "🎉"

        # Print a colorful message with rarity information
        print("\n" + "=" * 60)
        print(
            f"{rarity_emoji} NEW {nft.gift_name.upper()} NFT FOUND! {rarity_emoji}  {nft.name} {nft.full_id} {nft.url}"
        )

        # Print rarity information if available
        if nft.rarity:
            print("\nRarity Information:")
            for prop, info in nft.rarity.items():
                rarity_str = f" ({info['rarity']})" if info["rarity"] else ""

                # Highlight rare properties
                is_rare_prop = False
                try:
                    if info["rarity"]:
                        rarity_value = float(
                            info["rarity"].strip().replace("%", "").replace(",", ".")
                        )
                        if rarity_value < 0.6:
                            is_rare_prop = "🔥🔥 SUPER RARE"
                        elif rarity_value < 1.8:
                            is_rare_prop = "🔥 RARE"
                except (ValueError, TypeError):
                    pass

                print(
                    f"  - {prop}: {info['value']}{rarity_str} {is_rare_prop if is_rare_prop else ''}"
                )

        print("=" * 60 + "\n")
