from core.adb_driver import AdbDriver, get_driver_performance
from config import DEVICE_ID

if __name__ == "__main__":
    driver = AdbDriver(DEVICE_ID)
    performance = get_driver_performance(driver)
    if performance:
        print("Performance Test Results:")
        print(f"Average Screenshot Time: {performance['avg_screenshot_time']:.4f} seconds")
        print(f"Average Tap Time: {performance['avg_tap_time']:.4f} seconds")
        print(f'Average swipe time: {performance['avg_swipe_time']:.4f} seconds')