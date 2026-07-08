"""
====================================================
Vision Trading OS
Application Settings
====================================================
"""

import os
from dotenv import load_dotenv

# Load .env
load_dotenv()


class Settings:

    # Zerodha
    ZERODHA_API_KEY = os.getenv("ZERODHA_API_KEY", "")
    ZERODHA_API_SECRET = os.getenv("ZERODHA_API_SECRET", "")
    ZERODHA_ACCESS_TOKEN = os.getenv("ZERODHA_ACCESS_TOKEN", "")

    # Trading
    BROKER = os.getenv("BROKER", "ZERODHA")
    ENV = os.getenv("ENV", "DEVELOPMENT")

    # Dashboard
    WATCHLIST = [
        "NIFTY",
        "BANKNIFTY",
        "SENSEX",
    ]

    TIMEFRAME = "5m"

    VOICE_ENABLED = True

    AI_ENABLED = True


settings = Settings()