#!/usr/bin/env python3
import os
import re
import asyncio
import argparse
import logging
from collections import deque
import time
import httpx
import json
from environs import Env

from bs4 import BeautifulSoup
from aiohttp import ClientSession, ClientTimeout

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("nft-scanner")

# Load environment variables from .env file
env = Env()
env.read_env()

# Telegram configuration from environment
BOT_TOKEN = env.str("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = env.str("TELEGRAM_CHANNEL_ID")

if not BOT_TOKEN or not CHANNEL_ID:
    raise RuntimeError(
        "Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID in the .env file."
    )


class TelegramNotifier:
    def __init__(self, bot_token: str, channel_id: str):
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"

    async def send_message(self, text: str):
        url = f"{self.api_url}/sendMessage"
        payload = {"chat_id": self.channel_id, "text": text, "parse_mode": "HTML"}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload)
            logger.info(
                f"Telegram send_message status: {resp.status_code}, response: {resp.text}"
            )
            if resp.status_code != 200:
                logger.error(f"Failed to send message: {resp.text}")
            return resp

    async def send_document(self, file_bytes: bytes, filename: str, caption: str):
        url = f"{self.api_url}/sendDocument"
        files = {"document": (filename, file_bytes, "application/x-tgsticker")}
        data = {"chat_id": self.channel_id, "caption": caption}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=data, files=files)
            logger.info(
                f"Telegram send_document status: {resp.status_code}, response: {resp.text}"
            )
            if resp.status_code != 200:
                logger.error(f"Failed to send document: {resp.text}")
            return resp

    async def send_media_group(self, media: list):
        url = f"{self.api_url}/sendMediaGroup"
        data = {"chat_id": self.channel_id, "media": media}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=data)
            logger.info(
                f"Telegram sendMediaGroup status: {resp.status_code}, response: {resp.text}"
            )
            if resp.status_code != 200:
                logger.error(f"Failed to send media group: {resp.text}")
            return resp


class NFTScanner:
    def __init__(
        self,
        start_id=245,
        max_nfts=20,
        output_dir="nft_images",
        find_latest=False,
        monitor=False,
        check_interval=5,
        gift_name="SnakeBox",
        respect_saved=False,
    ):
        self.start_id = start_id
        self.current_id = start_id  # Will be updated by _load_last_id if available
        self.max_nfts = max_nfts
        self.output_dir = output_dir
        self.gift_name = gift_name
        self.base_url = "https://t.me/nft/"
        self.found_nfts = deque(maxlen=max_nfts)
        self.find_latest = find_latest
        self.monitor = monitor
        self.check_interval = check_interval
        self.timeout = ClientTimeout(total=5)  # 5 second timeout for requests
        self.notifier = TelegramNotifier(BOT_TOKEN, CHANNEL_ID)
        self.respect_saved = respect_saved

        # Flag to track if we loaded data from file
        self._loaded_from_file = False

        # Use absolute path to ensure files are stored in a consistent location
        # Use a path that will be persisted in Docker by mounting a volume
        self.data_dir = (
            "./app/data"  # This directory should be mounted as a volume in Docker
        )
        os.makedirs(self.data_dir, exist_ok=True)
        self.last_id_file = os.path.join(
            self.data_dir, f"last_id_{self.gift_name.lower()}.json"
        )

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # First load last checked ID from file if it exists
        self._load_last_id()

        # Respect the start_id argument by taking the maximum of saved ID and start_id
        # This ensures we never go backward even if start_id is specified
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
        """Load the last processed NFT ID from file"""
        if os.path.exists(self.last_id_file):
            try:
                with open(self.last_id_file, "r") as f:
                    data = json.load(f)
                    last_id = data.get("last_id")
                    if last_id is not None:
                        next_id = int(last_id) + 1  # Start from the next ID
                        self.current_id = next_id
                        logger.info(
                            f"Loaded last checked NFT ID for {self.gift_name}: {last_id}, starting from {next_id}"
                        )
                        self._loaded_from_file = True
                        return True
            except Exception as e:
                logger.error(f"Failed to load last ID from {self.last_id_file}: {e}")
                # Create a backup of the corrupted file
                if os.path.exists(self.last_id_file):
                    backup_path = f"{self.last_id_file}.backup"
                    try:
                        import shutil

                        shutil.copy2(self.last_id_file, backup_path)
                        logger.info(f"Created backup of corrupted file: {backup_path}")
                    except Exception as e2:
                        logger.error(f"Failed to create backup of corrupted file: {e2}")
        else:
            logger.info(
                f"No saved state file found at {self.last_id_file}, starting with initial ID"
            )
        self._loaded_from_file = False
        return False

    def _save_last_id(self, last_id):
        try:
            # First write to a temporary file, then rename to avoid corruption
            temp_file = f"{self.last_id_file}.tmp"
            with open(temp_file, "w") as f:
                json.dump({"last_id": last_id, "timestamp": time.time()}, f)

            # Rename the temp file to the actual file (atomic operation on most filesystems)
            import os

            os.replace(temp_file, self.last_id_file)

            logger.info(f"Saved last checked NFT ID for {self.gift_name}: {last_id}")
        except Exception as e:
            logger.error(f"Failed to save last ID to {self.last_id_file}: {e}")

    async def find_latest_nft_id(self, session):
        """Use a binary search-like approach to quickly find the latest NFT ID"""
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
                exists = await self.nft_exists_with_content_check(test_id, session)

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
            exists = await self.nft_exists_with_content_check(current_id, session)
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

            exists = await self.nft_exists_with_content_check(mid, session)
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

    async def nft_exists(self, nft_id, session):
        """Check if an NFT with the given ID exists based on HTTP status"""
        url = f"{self.base_url}SnakeBox-{nft_id}"
        try:
            async with session.get(url, timeout=self.timeout) as response:
                return response.status == 200
        except asyncio.TimeoutError:
            logger.warning(f"Request for ID {nft_id} timed out")
            return False
        except Exception as e:
            logger.warning(f"Error checking NFT {nft_id}: {e}")
            return False

    async def nft_exists_with_content_check(self, nft_id, session):
        """Check if an NFT with the given ID exists by examining page content"""
        url = f"{self.base_url}{self.gift_name}-{nft_id}"
        try:
            async with session.get(url, timeout=self.timeout) as response:
                if response.status != 200:
                    return False

                # Check content to verify it's a valid NFT page
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")

                # Look for NFT-specific elements
                nft_name_element = soup.select_one("text[font-size='23']")
                nft_id_element = soup.select_one("text[font-size='15']")

                # Check for characteristic elements of a valid NFT page
                if nft_name_element and nft_id_element:
                    # Verify it's a valid collectible ID by checking the text
                    if "Collectible #" in nft_id_element.text:
                        return True

                return False

        except asyncio.TimeoutError:
            logger.warning(f"Request for ID {nft_id} timed out")
            return False
        except Exception as e:
            logger.warning(f"Error checking NFT {nft_id}: {e}")
            return False

    async def check_nft(self, nft_id, session):
        """Check if NFT with given ID exists and extract its data"""
        url = f"{self.base_url}{self.gift_name}-{nft_id}"
        try:
            async with session.get(url, timeout=self.timeout) as response:
                if response.status != 200:
                    return None

                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")

                # Extract NFT name
                name_element = soup.select_one("text[font-size='23']")
                if not name_element:
                    return None
                nft_name = name_element.text.strip()

                # Extract NFT full ID (including collection number)
                id_element = soup.select_one("text[font-size='15']")
                if not id_element:
                    return None
                full_id = id_element.text.strip()
                # Extract just the numeric part
                id_match = re.search(r"#(\d+)", full_id)
                if not id_match:
                    nft_number = nft_id
                else:
                    nft_number = id_match.group(1)

                # Extract image URL
                image_element = soup.select_one(
                    "picture.tgme_gift_model source[type='application/x-tgsticker']"
                )
                if not image_element:
                    # Try the SVG version if TGS sticker not found
                    image_element = soup.select_one(
                        "picture.tgme_gift_model source[type='image/svg+xml']"
                    )
                    if not image_element:
                        return None

                image_url = image_element.get("srcset", "")

                # If it's a data URI, we'll need to handle it differently
                if isinstance(image_url, str) and image_url.startswith("data:"):
                    image_type = "svg"
                    image_data = image_url
                else:
                    image_type = (
                        "tgs"
                        if isinstance(image_url, str) and "sticker.tgs" in image_url
                        else "unknown"
                    )

                # Extract rarity information
                rarity_info = self.extract_rarity_info(soup)

                return {
                    "id": nft_id,
                    "name": nft_name,
                    "full_id": full_id,
                    "image_url": image_url,
                    "image_type": image_type,
                    "rarity": rarity_info,
                    "gift_name": self.gift_name,
                }

        except Exception as e:
            logger.error(f"Error checking NFT {nft_id}: {e}")
            return None

    def extract_rarity_info(self, soup):
        """Extract rarity information from the NFT page"""
        rarity_info = {}

        # Find the rarity table
        rarity_table = soup.select_one(".tgme_gift_table")
        if not rarity_table:
            return rarity_info

        # Extract rows from the table
        rows = rarity_table.select("tr")
        for row in rows:
            # Each row has a header (property name) and value with possible rarity percentage
            header = row.select_one("th")
            value_cell = row.select_one("td")

            if header and value_cell:
                property_name = header.text.strip()

                # Check if there's a rarity mark
                rarity_mark = value_cell.select_one("mark")
                if rarity_mark:
                    # Extract the property value without the rarity percentage
                    property_value = (
                        value_cell.get_text().replace(rarity_mark.text, "").strip()
                    )
                    rarity_percentage = rarity_mark.text.strip()
                else:
                    property_value = value_cell.text.strip()
                    rarity_percentage = None

                rarity_info[property_name] = {
                    "value": property_value,
                    "rarity": rarity_percentage,
                }

        return rarity_info

    async def download_image(self, nft_data, session):
        """Download NFT image and save it to the output directory"""
        try:
            filename = f"{self.gift_name.lower()}-{nft_data['name'].lower().replace(' ', '-')}-{nft_data['id']}"

            # Handle data URI (SVG)
            image_url = nft_data["image_url"]
            if isinstance(image_url, str) and image_url.startswith("data:"):
                # Extract the base64 data
                match = re.search(r"base64,(.+)", image_url)
                if match:
                    import base64

                    svg_data = base64.b64decode(match.group(1))
                    with open(
                        os.path.join(self.output_dir, f"{filename}.svg"), "wb"
                    ) as f:
                        f.write(svg_data)
                    logger.info(
                        f"Saved SVG image for {nft_data['name']} #{nft_data['id']}"
                    )
                    return True
                return False

            # Download regular URL
            file_extension = ".tgs" if nft_data["image_type"] == "tgs" else ".png"
            filepath = os.path.join(self.output_dir, f"{filename}{file_extension}")

            async with session.get(image_url, timeout=self.timeout) as response:
                if response.status != 200:
                    logger.error(
                        f"Failed to download image for NFT {nft_data['id']}: HTTP {response.status}"
                    )
                    return False

                image_data = await response.read()
                with open(filepath, "wb") as f:
                    f.write(image_data)

                logger.info(
                    f"Downloaded image for {nft_data['name']} #{nft_data['id']}"
                )
                # Do NOT send to Telegram here (only in monitor mode)
                return True

        except Exception as e:
            logger.error(f"Error downloading image for NFT {nft_data['id']}: {e}")
            return False

    async def scan(self):
        """Main scanning function to find and download the latest NFTs"""
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

            while (
                valid_results < self.max_nfts
                and consecutive_empty < max_consecutive_empty
            ):
                logger.info(f"Checking NFT ID: {self.current_id}")

                nft_data = await self.check_nft(self.current_id, session)

                if nft_data:
                    logger.info(f"Found NFT: {nft_data['name']} {nft_data['full_id']}")
                    self.found_nfts.append(nft_data)
                    await self.download_image(nft_data, session)
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
                highest_id = max(nft["id"] for nft in self.found_nfts)
                self._save_last_id(highest_id)

            self.print_summary()

            # If monitoring mode is enabled, start continuous monitoring
            if self.monitor:
                await self.monitor_new_nfts(session)

    async def monitor_new_nfts(self, session):
        """Continuously monitor for new NFTs beyond the latest known ID, polling every 3 seconds and batching results."""
        if self.found_nfts:
            highest_id = max(nft["id"] for nft in self.found_nfts)
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
                    nft_data = await self.check_nft(poll_current, session)
                    if nft_data:
                        logger.info(
                            f"New NFT found and added to batch: {nft_data['name']} {nft_data['full_id']} (ID: {nft_data['id']})"
                        )
                        self.found_nfts.append(nft_data)
                        batch_nfts.append(nft_data)
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
                    next_id = max(nft["id"] for nft in batch_nfts) + 1
                    logger.info(f"Updated next ID to {next_id} for next polling cycle")

                    # Save the highest ID we've found
                    self._save_last_id(next_id - 1)
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

                # Send notifications for found NFTs
                if batch_nfts:
                    # Compose message with all NFT links
                    if len(batch_nfts) == 1:
                        # For a single NFT, include detailed information
                        nft = batch_nfts[0]
                        # Escape HTML special characters in the name
                        safe_name = (
                            nft["name"]
                            .replace("&", "&amp;")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;")
                        )

                        # Check if any property has rarity < 0.6%
                        is_super_rare = False
                        if nft.get("rarity"):
                            for prop, info in nft["rarity"].items():
                                if info.get("rarity"):
                                    try:
                                        rarity_text = (
                                            info["rarity"]
                                            .strip()
                                            .replace("%", "")
                                            .replace(",", ".")
                                        )
                                        rarity_value = float(rarity_text)
                                        if rarity_value < 0.6:
                                            is_super_rare = True
                                            break
                                    except (ValueError, TypeError):
                                        pass

                        # Add super_rare tag if applicable
                        super_rare_tag = " #super_rare" if is_super_rare else ""

                        message = (
                            f"<b>New NFT found:</b>\n"
                            f"<a href='https://t.me/nft/{nft['gift_name']}-{nft['id']}'>"
                            f"<code>{safe_name}</code> {nft['full_id']}</a>{super_rare_tag}"
                        )

                        # Add rarity information if available
                        if nft.get("rarity"):
                            message += "\n\n<b>Rarity Information:</b>"
                            for prop, info in nft["rarity"].items():
                                # Escape property values as well
                                safe_value = (
                                    info["value"]
                                    .replace("&", "&amp;")
                                    .replace("<", "&lt;")
                                    .replace(">", "&gt;")
                                )
                                rarity_str = (
                                    f" ({info['rarity']})" if info["rarity"] else ""
                                )
                                message += (
                                    f"\n• {prop}: <code>{safe_value}</code>{rarity_str}"
                                )
                    else:
                        # For multiple NFTs, just use links with escaped names
                        links = []
                        for nft in batch_nfts:
                            safe_name = (
                                nft["name"]
                                .replace("&", "&amp;")
                                .replace("<", "&lt;")
                                .replace(">", "&gt;")
                            )

                            # Check if any property has rarity < 0.6%
                            is_super_rare = False
                            if nft.get("rarity"):
                                for prop, info in nft["rarity"].items():
                                    if info.get("rarity"):
                                        try:
                                            rarity_text = (
                                                info["rarity"]
                                                .strip()
                                                .replace("%", "")
                                                .replace(",", ".")
                                            )
                                            rarity_value = float(rarity_text)
                                            if rarity_value < 0.6:
                                                is_super_rare = True
                                                break
                                        except (ValueError, TypeError):
                                            pass

                            # Add super_rare tag if applicable
                            super_rare_tag = " #super_rare" if is_super_rare else ""

                            links.append(
                                f"<a href='https://t.me/nft/{nft['gift_name']}-{nft['id']}'>"
                                f"<code>{safe_name}</code> {nft['full_id']}</a>{super_rare_tag}"
                            )
                        message = "<b>New NFTs found:</b>\n" + "\n".join(links)

                    await self.notifier.send_message(message)

                    # Filter for Model == 'Neo Matrix' and Model rarity <= 2.1%
                    filtered_nfts = []
                    for nft in batch_nfts:
                        try:
                            # Get rarity info in a more robust way
                            model_info = nft.get("rarity", {}).get("Model", {})
                            model_name = model_info.get("value", "")
                            model_rarity = model_info.get("rarity", "100%")

                            # Clean and parse the rarity value
                            rarity_text = (
                                model_rarity.strip().replace("%", "").replace(",", ".")
                            )
                            if rarity_text:
                                rarity_value = float(rarity_text)
                            else:
                                rarity_value = 100.0

                            # Check if this is a Neo Matrix model with required rarity
                            if (
                                model_name == "Neo Matrix"
                                and rarity_value <= 2.1
                                and nft["image_type"] == "tgs"
                            ):
                                filtered_nfts.append(nft)
                                logger.info(
                                    f"Found qualifying Neo Matrix NFT with rarity {rarity_value}%"
                                )
                        except Exception as e:
                            logger.error(
                                f"Error processing rarity for NFT {nft['id']}: {str(e)}"
                            )
                            continue

                    # Prepare media group for Telegram (must be file_id or attach:// for new uploads)
                    if filtered_nfts:
                        logger.info(
                            f"Found {len(filtered_nfts)} NFTs that match Neo Matrix filtering criteria"
                        )
                        try:
                            # First download all stickers
                            media = []
                            files = {}

                            for idx, nft in enumerate(filtered_nfts):
                                try:
                                    image_url = nft["image_url"]
                                    async with httpx.AsyncClient() as client:
                                        resp = await client.get(image_url)
                                        if resp.status_code == 200:
                                            attach_name = f"file{idx}.tgs"
                                            files[attach_name] = resp.content

                                            # Get model info safely
                                            model_info = nft.get("rarity", {}).get(
                                                "Model", {}
                                            )
                                            model_name = model_info.get("value", "")
                                            model_rarity = model_info.get(
                                                "rarity", "100%"
                                            )

                                            # Create safe caption without potentially problematic characters
                                            caption = f"{nft['name']} {nft['full_id']}\nModel: {model_name}"
                                            if model_rarity:
                                                caption += f" (Rarity: {model_rarity})"

                                            media.append(
                                                {
                                                    "type": "document",
                                                    "media": f"attach://{attach_name}",
                                                    "caption": caption,
                                                }
                                            )
                                except Exception as e:
                                    logger.error(
                                        f"Error preparing media for NFT {nft['id']}: {str(e)}"
                                    )

                            # Now send the media
                            if media:
                                logger.info(
                                    f"Sending {len(media)} Neo Matrix NFTs to Telegram"
                                )
                                if len(media) == 1:
                                    # For single documents, use sendDocument
                                    attach_name = "file0.tgs"
                                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
                                    data = {
                                        "chat_id": CHANNEL_ID,
                                        "caption": media[0]["caption"],
                                        "parse_mode": "HTML",
                                    }
                                    files_payload = {
                                        "document": (
                                            attach_name,
                                            files[attach_name],
                                            "application/x-tgsticker",
                                        )
                                    }
                                    async with httpx.AsyncClient() as client:
                                        resp = await client.post(
                                            url, data=data, files=files_payload
                                        )
                                        logger.info(
                                            f"Telegram sendDocument status: {resp.status_code}, response: {resp.text}"
                                        )
                                else:
                                    # For multiple documents, use sendMediaGroup
                                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"
                                    data = {
                                        "chat_id": CHANNEL_ID,
                                        "media": json.dumps(media),
                                    }
                                    files_payload = {
                                        name: (name, content, "application/x-tgsticker")
                                        for name, content in files.items()
                                    }
                                    async with httpx.AsyncClient() as client:
                                        resp = await client.post(
                                            url, data=data, files=files_payload
                                        )
                                        logger.info(
                                            f"Telegram sendMediaGroup status: {resp.status_code}, response: {resp.text}"
                                        )
                        except Exception as e:
                            logger.error(f"Error sending media group: {str(e)}")
                            # Try to send one by one if group send fails
                            logger.info("Attempting to send documents one by one...")
                            for idx, nft in enumerate(filtered_nfts):
                                try:
                                    attach_name = f"file{idx}.tgs"
                                    if attach_name in files:
                                        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
                                        data = {
                                            "chat_id": CHANNEL_ID,
                                            "caption": f"{nft['name']} {nft['full_id']}",
                                            "parse_mode": "HTML",
                                        }
                                        file_payload = {
                                            "document": (
                                                attach_name,
                                                files[attach_name],
                                                "application/x-tgsticker",
                                            )
                                        }
                                        async with httpx.AsyncClient() as client:
                                            resp = await client.post(
                                                url, data=data, files=file_payload
                                            )
                                            logger.info(
                                                f"Individual document send status: {resp.status_code}"
                                            )
                                        await asyncio.sleep(
                                            1
                                        )  # Short delay between sends
                                except Exception as inner_e:
                                    logger.error(
                                        f"Failed to send individual document: {str(inner_e)}"
                                    )
                else:
                    # Slow down polling if nothing is found to avoid hammering the server
                    logger.info(
                        "No new NFTs found in this polling period. Waiting 5 seconds..."
                    )
                    await asyncio.sleep(5)  # Rest longer when no NFTs are found

        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user.")
        except Exception as e:
            logger.error(f"Error during monitoring: {e}")
            logger.exception("Full exception details:")

    def alert_new_nft(self, nft_data):
        """Make a sound and visual alert when a new NFT is found"""
        # Make a terminal beep sound (ASCII bell character)
        print("\a", flush=True)

        # For more visibility, print a special message with multiple beeps
        for _ in range(3):
            print("\a", end="", flush=True)
            time.sleep(0.3)

        # Print a colorful message with rarity information
        print("\n" + "=" * 60)
        print(
            f"🎉 NEW {nft_data['gift_name'].upper()} NFT FOUND! 🎉  {nft_data['name']} {nft_data['full_id']} https://t.me/nft/{nft_data['gift_name']}-{nft_data['id']}"
        )

        # Print rarity information if available
        if nft_data.get("rarity"):
            print("\nRarity Information:")
            for prop, info in nft_data["rarity"].items():
                rarity_str = f" ({info['rarity']})" if info["rarity"] else ""
                print(f"  - {prop}: {info['value']}{rarity_str}")

        print("=" * 60 + "\n")

    def print_summary(self):
        """Print a summary of the found NFTs"""
        print("\n===== NFT SCANNER SUMMARY =====")
        print(f"Found {len(self.found_nfts)} NFTs:")
        for i, nft in enumerate(self.found_nfts, 1):
            print(f"\n{i}. {nft['name']} {nft['full_id']}")

            # Print rarity information if available
            if nft.get("rarity"):
                for prop, info in nft["rarity"].items():
                    rarity_str = f" ({info['rarity']})" if info["rarity"] else ""
                    print(f"   - {prop}: {info['value']}{rarity_str}")

        print(f"\nImages saved to: {os.path.abspath(self.output_dir)}")
        print("==============================\n")


async def main():
    parser = argparse.ArgumentParser(description="Telegram NFT Scanner")
    parser.add_argument("--start", type=int, default=245, help="Starting NFT ID")
    parser.add_argument("--count", type=int, default=20, help="Number of NFTs to find")
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
    args = parser.parse_args()

    # In Docker environments, we always want to respect saved IDs
    # This ensures continuity between container restarts
    if os.path.exists("/app/data"):
        args.respect_saved = True
        logger.info("Docker environment detected, enabling --respect-saved option")

    scanner = NFTScanner(
        start_id=args.start,
        max_nfts=args.count,
        output_dir=args.output,
        find_latest=args.find_latest,
        monitor=args.monitor,
        check_interval=args.interval,
        gift_name=args.gift_name,
        respect_saved=args.respect_saved,
    )
    await scanner.scan()


if __name__ == "__main__":
    asyncio.run(main())
