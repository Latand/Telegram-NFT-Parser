"""Utilities for downloading and saving NFT images."""

import os
import re
import base64
from typing import Optional

from aiohttp import ClientSession

from src.nft_scanner.models import NFT
from src.nft_scanner.utils import setup_logger

logger = setup_logger("image-handler")


class ImageHandler:
    """Handles downloading and saving NFT images."""

    def __init__(self, output_dir: str = "nft_images"):
        """
        Initialize the image handler.

        Args:
            output_dir: Directory to save images to
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    async def download_image(self, nft: NFT, session: ClientSession) -> Optional[str]:
        """
        Download an NFT image and save it to the output directory.

        Args:
            nft: NFT to download image for
            session: ClientSession to use for downloading

        Returns:
            Path to saved image file or None if download failed
        """
        try:
            filepath = os.path.join(
                self.output_dir, f"{nft.filename}{nft.file_extension}"
            )

            # Handle data URI (SVG)
            if isinstance(nft.image_url, str) and nft.image_url.startswith("data:"):
                # Extract the base64 data
                match = re.search(r"base64,(.+)", nft.image_url)
                if match:
                    svg_data = base64.b64decode(match.group(1))
                    with open(filepath, "wb") as f:
                        f.write(svg_data)
                    logger.info(f"Saved SVG image for {nft.name} #{nft.id}")
                    return filepath
                return None

            # Download image from URL
            async with session.get(nft.image_url) as response:
                if response.status != 200:
                    logger.error(
                        f"Failed to download image for NFT {nft.id}: HTTP {response.status}"
                    )
                    return None

                image_data = await response.read()
                with open(filepath, "wb") as f:
                    f.write(image_data)

                logger.info(f"Downloaded image for {nft.name} #{nft.id}")
                return filepath

        except Exception as e:
            logger.error(f"Error downloading image for NFT {nft.id}: {e}")
            return None
