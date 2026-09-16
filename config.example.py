# -*- coding: utf-8 -*-
# Copy this file to config.py and fill in your own values.
# config.py is gitignored — it never gets committed.
import os

# Game accounts — one entry per simulator instance to run in parallel.
ACCOUNTS = [
    {
        'user_id': 'player1',
        'device_id': '172.29.160.1:5555',
        # Omit 'enabled_tasks' to run all cycle tasks (help, dig, lucky_gift, rally).
        # 'launch' always runs and cannot be disabled.
        # List only the tasks you want active for this account:
        # 'enabled_tasks': ['help', 'dig'],
        # 'rally_preference' : [
        #     {
        #         'name': 'DE', # Doom Elite
        #         'enabled': False,
        #         'level': 30
        #     },
        #     {
        #         'name': 'DW', # Doom Walker
        #         'enabled': False,
        #         'level': 170
        #     },
        #     {
        #         'name': 'ZB', # Zombie Boss
        #         'enabled': True,
        #         'level': 70
        #     }
        # ]
    },
    # {
    #     'user_id': 'player2',
    #     'device_id': '172.29.160.1:5556',
    #     'enabled_tasks': ['help', 'lucky_gift'],
    # },
]

# Legacy alias used by capture_tool.py; derived from the first account.
DEVICE_ID = ACCOUNTS[0]['device_id']

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

# IAM: map each chat id to its access level.
#   'admin'        — full access to all game accounts
#   ['user_id', …] — restricted to the listed accounts only
# Leave empty and send any message to the bot to discover your chat id.
TELEGRAM_CHAT_ACCESS = {
    # 123456789: 'admin',
    # 987654321: ['player1'],
}

# Legacy alias — all chat ids listed here are treated as admins.
# Ignored when TELEGRAM_CHAT_ACCESS is non-empty for the same chat id.
TELEGRAM_ALLOWED_CHATS = []
