"""HTML parsing utilities for the NFT scanner."""

import re
from typing import Dict, Optional

from bs4 import BeautifulSoup

from src.nft_scanner.models import NFT


def extract_rarity_info(soup: BeautifulSoup) -> Dict[str, Dict[str, str]]:
    """
    Extract rarity information from the NFT page.

    Args:
        soup: BeautifulSoup object of the NFT page

    Returns:
        Dictionary of rarity information
    """
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


def parse_nft_page(html: str, nft_id: int, gift_name: str) -> Optional[NFT]:
    """
    Parse HTML page and extract NFT data.

    Args:
        html: HTML content of the NFT page
        nft_id: ID of the NFT
        gift_name: Name of the NFT gift collection

    Returns:
        NFT object if parsing was successful, None otherwise
    """
    try:
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
        nft_number = nft_id if not id_match else id_match.group(1)

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
        else:
            image_type = (
                "tgs"
                if isinstance(image_url, str) and "sticker.tgs" in image_url
                else "unknown"
            )

        # Extract rarity information
        rarity_info = extract_rarity_info(soup)

        # Create NFT object
        nft = NFT(
            id=nft_id,
            name=nft_name,
            full_id=full_id,
            image_url=image_url,
            image_type=image_type,
            rarity=rarity_info,
            gift_name=gift_name,
        )

        # Analyze rarity
        nft.determine_super_rarity()

        return nft

    except Exception:
        # Log error and return None
        return None
