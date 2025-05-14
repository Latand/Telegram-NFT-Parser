"""Logging configuration for the NFT scanner."""

import logging
from typing import Optional


def setup_logger(
    name: str = "nft-scanner", level: Optional[int] = None
) -> logging.Logger:
    """
    Set up and return a logger with the specified name and level.

    Args:
        name: Name of the logger
        level: Logging level (defaults to INFO)

    Returns:
        Configured logger
    """
    if level is None:
        level = logging.INFO

    logger = logging.getLogger(name)

    # Only set up handlers if they don't exist yet to avoid duplicate messages
    if not logger.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    logger.setLevel(level)
    return logger
