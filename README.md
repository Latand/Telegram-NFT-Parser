# Telegram NFT Scanner

A Python script that tracks and downloads Telegram NFTs. The script scans for the latest NFTs by checking sequential IDs, and downloads their images when found.

## Features

- Scans Telegram NFT pages with sequential IDs
- Downloads NFT images (TGS stickers or SVG)
- Customizable starting ID and number of NFTs to find
- Asynchronous for efficient operation
- Docker support for continuous monitoring

## Requirements

- Python 3.7+
- aiohttp
- beautifulsoup4

## Installation

1. Clone this repository
2. Create a virtual environment and install dependencies using uv:

```bash
# Install uv if you don't have it
pip install uv

# Create virtual environment and install dependencies
uv venv
uv pip install -r requirements.txt
```

3. Create a `.env` file at the root level with the following variables:

```
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHANNEL_ID=your_channel_id_here
```

## Usage

```bash
# Basic usage (starts from ID 245, finds 20 NFTs)
python nft_scanner.py

# Custom start ID
python nft_scanner.py --start 300

# Custom number of NFTs to find
python nft_scanner.py --count 10

# Custom output directory
python nft_scanner.py --output my_nfts
```

### Command Line Arguments

- `--start`: Starting NFT ID (default: 245)
- `--count`: Number of NFTs to find (default: 20)
- `--output`: Output directory for NFT images (default: nft_images)
- `--gift-name`: Specific NFT gift name to track
- `--monitor`: Run in monitoring mode
- `--find-latest`: Find the latest NFT ID

## Docker Usage

To run the trackers using Docker:

```bash
# First create a .env file with your Telegram credentials
# Then run:
docker-compose up -d
```

## Output

The script creates a directory with the specified name (default: `nft_images`) and saves the NFT images with filenames in the format `nft-name-id.extension`.

After scanning, it prints a summary of the found NFTs.
