#!/usr/bin/env python3
"""
Telegram bot setup helper.
Tests the Telegram bot connection and sends a verification message.

Usage:
    python scripts/setup_telegram.py
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


async def main():
    """Test Telegram bot configuration."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    print("TradingView Webhook Bot - Telegram Setup")
    print("=" * 45)

    if not token:
        print("\nNo TELEGRAM_BOT_TOKEN found in .env file.")
        print("\nTo set up Telegram notifications:")
        print("1. Open Telegram and search for @BotFather")
        print("2. Send /newbot and follow the instructions")
        print("3. Copy the bot token to your .env file:")
        print("   TELEGRAM_BOT_TOKEN=your_token_here")
        return

    if not chat_id:
        print("\nNo TELEGRAM_CHAT_ID found in .env file.")
        print("\nTo get your chat ID:")
        print("1. Open Telegram and search for @userinfobot")
        print("2. Send /start to get your chat ID")
        print("3. Copy the chat ID to your .env file:")
        print("   TELEGRAM_CHAT_ID=your_chat_id_here")
        return

    print(f"\nBot Token: {token[:10]}...{token[-5:]}")
    print(f"Chat ID:   {chat_id}")

    # Test the bot connection
    from src.notifications.telegram import TelegramNotifier

    notifier = TelegramNotifier({"telegram_enabled": True})
    notifier._token = token
    notifier._chat_id = chat_id

    print("\nTesting bot connection...")
    info = await notifier.test_connection()

    if info.get("ok"):
        print(f"Bot Name:     {info['bot_name']}")
        print(f"Bot Username: @{info['bot_username']}")
        print("\nConnection successful!")

        # Send a test message
        print("\nSending test message...")
        test_msg = (
            "SETUP COMPLETE\n"
            "TradingView Webhook Bot is connected!\n"
            "You will receive trade notifications here."
        )
        success = await notifier.send(test_msg)

        if success:
            print("Test message sent! Check your Telegram.")
        else:
            print("Failed to send test message.")
            print("Make sure you have started a conversation with the bot first.")
    else:
        print(f"Connection failed: {info.get('error', 'Unknown error')}")
        print("\nPlease verify your bot token is correct.")

    await notifier.close()


if __name__ == "__main__":
    asyncio.run(main())
