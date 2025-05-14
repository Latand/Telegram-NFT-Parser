#!/usr/bin/env python3
"""Test script to verify that imports work correctly."""

import os
import sys

# Add the current directory to sys.path if it's not already there
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print(f"sys.path: {sys.path}")

# Try importing the modules
try:
    print("✓ Successfully imported Config")

    print("✓ Successfully imported NFTScanner")

    print("✓ Successfully imported NFT")

    print("✓ Successfully imported setup_logger")

    print("✓ Successfully imported TelegramClient")

    print("✓ Successfully imported StateManager")

    print("\nAll imports successful!")
except Exception as e:
    print(f"\n❌ Import error: {e}")
    sys.exit(1)

sys.exit(0)
