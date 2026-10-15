from core.mumu_driver import MuMu12IPC
import time

def test_swipe_up(driver):
    start = time.perf_counter()
    driver.swipe(450, 400, 450, 1200, 900, 30)
    end = time.perf_counter()
    print(f'Swipe finished in: {end-start:.3f}')

if __name__ == '__main__':
    driver = MuMu12IPC(simulator_index=0)
    test_swipe_up(driver)