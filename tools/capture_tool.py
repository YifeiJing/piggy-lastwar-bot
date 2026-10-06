# -*- coding: utf-8 -*-
import os
import time
import cv2
import sys
from config import DEVICE_ID, ASSETS_DIR, DUMP_DIR
from core.mumu_driver import MuMu12IPC
from vision.matcher import TemplateMatcher, measure_template_matching_performance
from vision.ocr import OCREngine, measure_ocr_performance

def main():
    print(f"[*] Capturing screen from {DEVICE_ID}...")
    driver = MuMu12IPC(simulator_index=0)
    driver.connect()
    start_time = time.perf_counter()
    img = driver.screenshot()
    end_time = time.perf_counter()
    print(f"[*] Screenshot captured in {end_time - start_time:.6f} seconds.")

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

def capture_perf_estimation():
    driver = AdbDriver(device_id=DEVICE_ID)
    iterations = 10
    total_time = 0.0

    for i in range(iterations):
        start_time = time.perf_counter()
        img = driver.screenshot()
        end_time = time.perf_counter()
        elapsed_time = end_time - start_time
        total_time += elapsed_time
        print(f"Iteration {i + 1}: Screenshot captured in {elapsed_time:.6f} seconds.")

    average_time = total_time / iterations
    print(f"Average screenshot capture time over {iterations} iterations: {average_time:.6f} seconds.")

def measure_template_matching_performance_on_latest(template_path: str, threshold: float = 0.82, iterations: int = 10):
    latest_path = os.path.join(ASSETS_DIR, 'latest_screen.png')
    if not os.path.exists(latest_path):
        print(f"[-] Latest screen capture not found at {latest_path}. Please run the capture tool first.")
        return

    img = cv2.imread(latest_path)
    if img is None:
        print(f"[-] Failed to read the latest screen capture from {latest_path}.")
        return

    average_time = measure_template_matching_performance(img, template_path, threshold, iterations, scan_range=(708,1450,890,1585))
    print(f"Average template matching time over {iterations} iterations: {average_time:.6f} seconds.")

def measure_ocr_performance_on_latest(iterations: int = 10):
    latest_path = os.path.join(ASSETS_DIR, 'latest_screen.png')
    if not os.path.exists(latest_path):
        print(f"[-] Latest screen capture not found at {latest_path}. Please run the capture tool first.")
        return

    img = cv2.imread(latest_path)
    if img is None:
        print(f"[-] Failed to read the latest screen capture from {latest_path}.")
        return

    average_time = measure_ocr_performance(img, iterations)
    print(f"Average OCR time over {iterations} iterations: {average_time:.6f} seconds.")

def measure_template_matching_tap_performance(template_path: str, threshold: float = 0.82, iterations: int = 5, scan_range=None):
    matcher = TemplateMatcher()
    total_time = 0.0
    driver = MuMu12IPC(simulator_index=0)
    driver.connect()
    img = driver.screenshot()
    pos = matcher.find_template(img, template_path, scan_area=scan_range)
    for i in range(iterations):
        start_time = time.perf_counter()
        if pos is not None:
            driver.tap(pos[0], pos[1], sleep_time=None)
        end_time = time.perf_counter()
        elapsed_time = end_time - start_time
        total_time += elapsed_time
        print(f"Iteration {i + 1}: Template matching completed in {elapsed_time:.6f} seconds. Position found: {pos}")

    average_time = total_time / iterations
    return average_time

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--perf':
        capture_perf_estimation()
    elif len(sys.argv) > 1 and sys.argv[1] == '--match-perf':
        template_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ASSETS_DIR, 'template.png')
        measure_template_matching_performance_on_latest(template_path)
    elif len(sys.argv) > 1 and sys.argv[1] == '--ocr-perf':
        measure_ocr_performance_on_latest()
    elif len(sys.argv) > 1 and sys.argv[1] == '--match-tap-perf':
        template_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ASSETS_DIR, 'template.png')
        average_time = measure_template_matching_tap_performance(template_path, iterations=8, scan_range=(450,800,800,1500))
        print(f"Average template matching and tap time over iterations: {average_time:.6f} seconds.")
    else:
        main()
