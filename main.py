# -*- coding: utf-8 -*-
from config import DEVICE_ID, TELEGRAM_BOT_TOKEN
from core.adb_driver import AdbDriver
from core.engine import BotEngine
from telegram_controller import TelegramController


def main():
    print("==========================================")
    print("       Last War: Survival Bot Engine       ")
    print("==========================================")

    driver = AdbDriver(device_id=DEVICE_ID)
    engine = BotEngine(driver, cycle_interval=1.0)

    if TELEGRAM_BOT_TOKEN:
        controller = TelegramController(engine, driver)
        engine.set_notifier(controller.send_message)
        engine.start()
        controller.run()  # blocks (polling) until Ctrl+C
    else:
        print("[!] TELEGRAM_BOT_TOKEN not set in config.py — running without remote control.")
        engine.start()
        engine.wait()


if __name__ == '__main__':
    main()
