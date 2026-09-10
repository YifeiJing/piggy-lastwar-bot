# -*- coding: utf-8 -*-
import os
import time
import cv2
from config import DEVICE_ID, ASSETS_DIR, DUMP_DIR
from core.adb_driver import AdbDriver


def main():
    print(f"[*] Capturing screen from {DEVICE_ID}...")
    driver = AdbDriver(device_id=DEVICE_ID)
    img = driver.screenshot()

    height, width, channels = img.shape
    print(f'Screen size: Height: {height}, Width: {width}')
    if img is None:
        print("[-] Screenshot failed. Verify ADB connection and port forwarding.")
        return

    timestamp = int(time.time())
    dump_filename = f"screen_{timestamp}.png"
    dump_path = os.path.join(DUMP_DIR, dump_filename)
    latest_path = os.path.join(ASSETS_DIR, 'latest_screen.png')

    cv2.imwrite(dump_path, img)
    cv2.imwrite(latest_path, img)

    print("[+] Captured successfully!")
    print(f"    - {latest_path}")
    print(f"    - {dump_path}")


if __name__ == '__main__':
    main()
