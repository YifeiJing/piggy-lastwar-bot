# -*- coding: utf-8 -*-
from config import TELEGRAM_BOT_TOKEN
from core.adb_driver import AdbDriver
from core.engine import BotEngine
from telegram_controller import TelegramController

try:
    from config import ACCOUNTS
except ImportError:
    # Backward compat: config.py predates ACCOUNTS, has a bare DEVICE_ID.
    from config import DEVICE_ID
    ACCOUNTS = [{'user_id': 'default', 'device_id': DEVICE_ID}]


def main():
    print("==========================================")
    print("       Last War: Survival Bot Engine       ")
    print("==========================================")

    engines = {}
    drivers = {}
    for acc in ACCOUNTS:
        uid = acc['user_id']
        drv = AdbDriver(device_id=acc['device_id'])
        eng = BotEngine(drv, cycle_interval=1.0, user_id=uid,
                        enabled_tasks=acc.get('enabled_tasks'))
        # load the ocr model once
        eng.ocr_engine._engine()
        engines[uid] = eng
        drivers[uid] = drv

    if TELEGRAM_BOT_TOKEN:
        controller = TelegramController(engines, drivers)
        for uid, eng in engines.items():
            eng.set_notifier(lambda text, u=uid: controller.send_message(text, u))
            eng.set_photo_notifier(lambda name, capture, u=uid: controller.send_capture(u, capture, name))
            eng.start()
        controller.run()  # blocks (polling) until Ctrl+C
    else:
        print("[!] TELEGRAM_BOT_TOKEN not set in config.py — running without remote control.")
        for eng in engines.values():
            eng.start()
        list(engines.values())[-1].wait()


if __name__ == '__main__':
    main()
