# Telegram NFT Scanner

A modular Python application for scanning, monitoring, and notifying about Telegram NFTs.

## Features

- Scan for NFTs on Telegram's website
- Monitor for new NFTs in real-time
- Send notifications to a Telegram channel
- Filter and notify about rare NFTs
- Download NFT images
- Persistent state between runs

## Project Structure

The project has been refactored for better maintainability with a modular architecture:

```
src/
├── main.py                    # Main entry point
├── nft_scanner/               # Main package
│   ├── __init__.py
│   ├── config.py              # Configuration handling
│   ├── clients/               # External API clients
│   │   ├── __init__.py
│   │   └── telegram.py        # Telegram API client
│   ├── core/                  # Core functionality
│   │   ├── __init__.py
│   │   └── scanner.py         # NFT scanner implementation
│   ├── models/                # Data models
│   │   ├── __init__.py
│   │   └── nft.py             # NFT data class
│   ├── storage/               # State persistence
│   │   ├── __init__.py
│   │   └── state_manager.py   # State management
│   └── utils/                 # Utility functions
│       ├── __init__.py
│       ├── html_parser.py     # HTML parsing utilities
│       ├── image_handler.py   # Image downloading
│       └── logging.py         # Logging setup
```

## Installation

1. Clone this repository:

   ```bash
   git clone https://github.com/yourusername/telegram-nft-scanner.git
   cd telegram-nft-scanner
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file with your Telegram bot credentials:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHANNEL_ID=your_telegram_channel_id
   ```

## Usage

### Basic Scanning

Run the scanner with default settings:

```bash
python src/main.py
```

### Advanced Options

```bash
python src/main.py --start 245 --count 20 --gift-name SnakeBox --find-latest --monitor
```

Available options:

- `--start`: Starting NFT ID (default: 245)
- `--count`: Number of NFTs to find (default: 20)
- `--output`: Output directory for NFT images (default: "nft_images")
- `--find-latest`: Use binary search to quickly find the latest NFT ID
- `--monitor`: Continuously monitor for new NFTs after initial scan
- `--interval`: Interval between checks when monitoring (default: 5 seconds)
- `--gift-name`: Gift name to track (default: "SnakeBox")
- `--respect-saved`: Always respect saved IDs and skip binary search when IDs are loaded from file
- `--data-dir`: Directory to store state files (default: "./data")

## Docker Support

You can also run the application using Docker:

```bash
docker-compose up -d
```

This will start the NFT scanner in monitoring mode with persistent storage.

## Rarity Detection

The scanner detects rare NFTs based on the "Model" property rarity value. NFTs with a Model rarity < 0.6% are marked as super rare and receive special notification treatment.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
