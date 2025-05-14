"""Telegram API client for sending NFT notifications."""

from typing import Dict, List

import httpx

from src.nft_scanner.models import NFT
from src.nft_scanner.utils import setup_logger

logger = setup_logger("telegram-client")


class TelegramClient:
    """Client for sending Telegram notifications about NFTs."""

    def __init__(self, bot_token: str, channel_id: str):
        """
        Initialize the Telegram client.

        Args:
            bot_token: Telegram bot token
            channel_id: Telegram channel ID to send messages to
        """
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Send a text message to the Telegram channel.

        Args:
            text: Text to send
            parse_mode: Parse mode for the message (HTML, Markdown, etc.)

        Returns:
            True if the message was sent successfully, False otherwise
        """
        url = f"{self.api_url}/sendMessage"
        payload = {"chat_id": self.channel_id, "text": text, "parse_mode": parse_mode}

        logger.info(f"Sending message to Telegram channel {self.channel_id}")

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json=payload)
                logger.info(
                    f"Telegram send_message status: {resp.status_code}, text length: {len(text)}"
                )

                if resp.status_code != 200:
                    logger.error(f"Failed to send message: {resp.text}")
                    return False

                logger.info("Successfully sent message to Telegram")
                return True
            except Exception as e:
                logger.error(f"Error sending message to Telegram: {str(e)}")
                return False

    async def send_document(
        self, file_bytes: bytes, filename: str, caption: str
    ) -> bool:
        """
        Send a document file to the Telegram channel.

        Args:
            file_bytes: Bytes of the file to send
            filename: Name of the file
            caption: Caption for the document

        Returns:
            True if the document was sent successfully, False otherwise
        """
        url = f"{self.api_url}/sendDocument"
        files = {"document": (filename, file_bytes, "application/x-tgsticker")}
        data = {"chat_id": self.channel_id, "caption": caption}

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, data=data, files=files)
                logger.info(f"Telegram send_document status: {resp.status_code}")

                if resp.status_code != 200:
                    logger.error(f"Failed to send document: {resp.text}")
                    return False
                return True
            except Exception as e:
                logger.error(f"Error sending document: {str(e)}")
                return False

    async def send_media_group(self, media: List[Dict]) -> bool:
        """
        Send a group of media files to the Telegram channel.

        Args:
            media: List of media objects to send

        Returns:
            True if the media group was sent successfully, False otherwise
        """
        url = f"{self.api_url}/sendMediaGroup"
        data = {"chat_id": self.channel_id, "media": media}

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json=data)
                logger.info(f"Telegram sendMediaGroup status: {resp.status_code}")

                if resp.status_code != 200:
                    logger.error(f"Failed to send media group: {resp.text}")
                    return False
                return True
            except Exception as e:
                logger.error(f"Error sending media group: {str(e)}")
                return False

    def _escape_html(self, text: str) -> str:
        """
        Escape HTML special characters in text.

        Args:
            text: Text to escape

        Returns:
            Escaped text
        """
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _is_model_super_rare(self, nft: NFT) -> bool:
        """
        Check if the NFT's model is super rare (rarity < 0.6%).

        Args:
            nft: NFT to check

        Returns:
            True if the model is super rare, False otherwise
        """
        if not nft.rarity or "Model" not in nft.rarity:
            return False

        model_info = nft.rarity["Model"]
        model_rarity = model_info.get("rarity")

        if not model_rarity:
            return False

        try:
            rarity_value = float(
                model_rarity.strip().replace("%", "").replace(",", ".")
            )
            return rarity_value < 0.6
        except (ValueError, TypeError):
            return False

    def _is_model_rare(self, nft: NFT) -> bool:
        """
        Check if the NFT's model is rare (rarity < 1.8% but not super rare).

        Args:
            nft: NFT to check

        Returns:
            True if the model is rare, False otherwise
        """
        if not nft.rarity or "Model" not in nft.rarity:
            return False

        model_info = nft.rarity["Model"]
        model_rarity = model_info.get("rarity")

        if not model_rarity:
            return False

        try:
            rarity_value = float(
                model_rarity.strip().replace("%", "").replace(",", ".")
            )
            return 0.6 <= rarity_value < 1.8
        except (ValueError, TypeError):
            return False

    def _get_model_rarity_tag(self, nft: NFT) -> str:
        """
        Get the rarity tag for an NFT based on its model rarity.

        Args:
            nft: NFT to get tag for

        Returns:
            Rarity tag or empty string
        """
        if self._is_model_super_rare(nft):
            model_info = nft.rarity["Model"]
            model_name = model_info.get("value", "")
            model_rarity = model_info.get("rarity", "")
            return f" #super_rare (Model: {model_name} {model_rarity})"
        elif self._is_model_rare(nft):
            model_info = nft.rarity["Model"]
            model_name = model_info.get("value", "")
            model_rarity = model_info.get("rarity", "")
            return f" #rare (Model: {model_name} {model_rarity})"
        return ""

    async def send_nft_notification(self, nft: NFT) -> bool:
        """
        Send a notification about a new NFT.

        Args:
            nft: NFT object to send notification about

        Returns:
            True if the notification was sent successfully, False otherwise
        """
        # Escape HTML special characters in the name
        safe_name = self._escape_html(nft.name)

        # Add super_rare tag if applicable (only based on model rarity)
        super_rare_tag = self._get_model_rarity_tag(nft)

        message = (
            f"<b>New NFT found:</b>\n"
            f"<a href='{nft.url}'>"
            f"<code>{safe_name}</code> {nft.full_id}</a>{super_rare_tag}"
        )

        # Add rarity information if available
        if nft.rarity:
            message += "\n\n<b>Rarity Information:</b>"
            for prop, info in nft.rarity.items():
                # Escape property values as well
                safe_value = self._escape_html(info["value"])
                rarity_str = f" ({info['rarity']})" if info["rarity"] else ""
                message += f"\n• {prop}: <code>{safe_value}</code>{rarity_str}"

        return await self.send_message(message)

    async def send_batch_notification(self, nfts: List[NFT]) -> bool:
        """
        Send a notification about multiple NFTs.
        When a single NFT is found, sends detailed information about it.
        Send notifications for ALL collectibles found, not just rare ones.

        Args:
            nfts: List of NFT objects to send notification about

        Returns:
            True if the notification was sent successfully, False otherwise
        """
        if not nfts:
            logger.warning("No NFTs provided for notification")
            return False

        # If only one NFT is found, send detailed information about it
        if len(nfts) == 1:
            logger.info(
                f"Sending detailed notification for single NFT: {nfts[0].name} {nfts[0].full_id}"
            )
            return await self.send_nft_notification(nfts[0])

        # For multiple NFTs, create a list of links
        logger.info(f"Sending batch notification for {len(nfts)} NFTs")
        links = []
        for nft in nfts:
            # Escape HTML special characters in the name
            safe_name = self._escape_html(nft.name)

            # Add super_rare tag if applicable (only based on model rarity)
            super_rare_tag = self._get_model_rarity_tag(nft)

            links.append(
                f"<a href='{nft.url}'>"
                f"<code>{safe_name}</code> {nft.full_id}</a>{super_rare_tag}"
            )

        message = "<b>New NFTs found:</b>\n" + "\n".join(links)
        logger.info(f"Created batch message with {len(links)} links")
        return await self.send_message(message)

    async def send_tgs_stickers(
        self, nfts: List[NFT], model_name: str = "Neo Matrix", max_rarity: float = 1.8
    ) -> bool:
        """
        Send TGS stickers for specific models with low rarity.

        Args:
            nfts: List of NFT objects to filter and send
            model_name: Model name to filter for
            max_rarity: Maximum rarity value to include (default: 1.8%)

        Returns:
            True if at least one sticker was sent successfully, False otherwise
        """
        # Filter for specific model and rarity
        filtered_nfts = []
        for nft in nfts:
            try:
                # Get model info
                if not nft.rarity or "Model" not in nft.rarity:
                    continue

                model_info = nft.rarity["Model"]
                model_name_value = model_info.get("value", "")
                model_rarity = model_info.get("rarity", "100%")

                # Clean and parse the rarity value
                rarity_text = model_rarity.strip().replace("%", "").replace(",", ".")
                if not rarity_text:
                    continue

                rarity_value = float(rarity_text)

                # Check if this is the specified model with required rarity
                if (
                    model_name_value == model_name
                    and rarity_value <= max_rarity
                    and nft.image_type == "tgs"
                ):
                    filtered_nfts.append(nft)
                    rarity_label = (
                        "super rare"
                        if rarity_value <= 0.6
                        else "rare"
                        if rarity_value <= 1.8
                        else "uncommon"
                    )
                    logger.info(
                        f"Found qualifying {model_name} NFT ({rarity_label}) with rarity {rarity_value}%"
                    )
            except Exception as e:
                logger.error(f"Error processing rarity for NFT {nft.id}: {str(e)}")

        if not filtered_nfts:
            return False

        # Download all stickers and prepare media array
        return await self._send_filtered_stickers(filtered_nfts)

    async def _send_filtered_stickers(self, nfts: List[NFT]) -> bool:
        """
        Download and send the filtered stickers.

        Args:
            nfts: List of filtered NFT objects to send

        Returns:
            True if at least one sticker was sent successfully, False otherwise
        """
        # First download all stickers
        media = []
        files = {}

        for idx, nft in enumerate(nfts):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(nft.image_url)
                    if resp.status_code == 200:
                        attach_name = f"file{idx}.tgs"
                        files[attach_name] = resp.content

                        # Get model info safely
                        model_info = nft.rarity.get("Model", {})
                        model_name_value = model_info.get("value", "")
                        model_rarity = model_info.get("rarity", "100%")

                        # Create safe caption
                        caption = f"{nft.name} {nft.full_id}\nModel: {model_name_value}"
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
                logger.error(f"Error preparing media for NFT {nft.id}: {str(e)}")

        if not media:
            return False

        return await self._send_media_files(media, files, nfts)

    async def _send_media_files(
        self, media: List[Dict], files: Dict, nfts: List[NFT]
    ) -> bool:
        """
        Send media files to Telegram.

        Args:
            media: List of media objects to send
            files: Dictionary of file contents
            nfts: List of NFT objects corresponding to the files

        Returns:
            True if at least one file was sent successfully, False otherwise
        """
        # Send the media
        model_name = nfts[0].rarity.get("Model", {}).get("value", "Unknown")
        logger.info(f"Sending {len(media)} {model_name} NFTs to Telegram")

        try:
            if len(media) == 1:
                # For single documents, use sendDocument
                attach_name = "file0.tgs"
                url = f"https://api.telegram.org/bot{self.bot_token}/sendDocument"
                data = {
                    "chat_id": self.channel_id,
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
                    resp = await client.post(url, data=data, files=files_payload)
                    logger.info(f"Telegram sendDocument status: {resp.status_code}")
                    return resp.status_code == 200
            else:
                # For multiple documents, use sendMediaGroup
                url = f"https://api.telegram.org/bot{self.bot_token}/sendMediaGroup"
                data = {
                    "chat_id": self.channel_id,
                    "media": media,
                }
                files_payload = {
                    name: (name, content, "application/x-tgsticker")
                    for name, content in files.items()
                }
                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, data=data, files=files_payload)
                    logger.info(f"Telegram sendMediaGroup status: {resp.status_code}")
                    return resp.status_code == 200
        except Exception as e:
            logger.error(f"Error sending media group: {str(e)}")
            return await self._send_files_individually(nfts, files)

    async def _send_files_individually(self, nfts: List[NFT], files: Dict) -> bool:
        """
        Send files individually if group send fails.

        Args:
            nfts: List of NFT objects to send
            files: Dictionary of file contents

        Returns:
            True if at least one file was sent successfully, False otherwise
        """
        # Try to send one by one if group send fails
        success = False
        logger.info("Attempting to send documents one by one...")

        for idx, nft in enumerate(nfts):
            try:
                attach_name = f"file{idx}.tgs"
                if attach_name in files:
                    url = f"https://api.telegram.org/bot{self.bot_token}/sendDocument"
                    data = {
                        "chat_id": self.channel_id,
                        "caption": f"{nft.name} {nft.full_id}",
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
                        resp = await client.post(url, data=data, files=file_payload)
                        if resp.status_code == 200:
                            success = True
                        logger.info(
                            f"Individual document send status: {resp.status_code}"
                        )
            except Exception as inner_e:
                logger.error(f"Failed to send individual document: {str(inner_e)}")

        return success
