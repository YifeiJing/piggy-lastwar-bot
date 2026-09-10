# -*- coding: utf-8 -*-
# Copy this file to config.py and fill in your own values.
# config.py is gitignored — it never gets committed.
import os

DEVICE_ID = '172.29.160.1:5555'

SCREEN_WIDTH = 1600
SCREEN_HEIGHT = 900

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
DUMP_DIR = os.path.join(BASE_DIR, 'dumps')
LOG_DIR = os.path.join(BASE_DIR, 'logs')
DIG_CAPTURE_DIR = os.path.join(BASE_DIR, 'dig_captures')

os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(DUMP_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DIG_CAPTURE_DIR, exist_ok=True)

# ---- Telegram remote control ----
# Create a bot with @BotFather and paste the token here.
TELEGRAM_BOT_TOKEN = ''

# Chat ids allowed to control the bot.
# Leave empty and send any message to the bot — it will reply with your chat id.
TELEGRAM_ALLOWED_CHATS = []
