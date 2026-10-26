# -*- coding: utf-8 -*-
import os
import time

import cv2
import numpy as np
from tasks.base_task import BaseTask
from config import ASSETS_DIR, DUMP_DIR, MODEL_DIR
from core.logger import save_capture
from enum import Enum
from vision.detector import GameObjectDetector

class MonsterType(Enum):
    DE = 'Doom Elite'
    DW = 'Doom Walker'
    ZB = 'Zombie'
    UN = 'UNKNOWN'

class DigType(Enum):
    Excavator = 'Excavator'
    Drone = 'Drone'
    UN = 'UNKNOWN'

class AllianceHelpTask(BaseTask):
    def run(self, trigger_pos=None):
        self._raise_if_killed()
        if trigger_pos is not None:
            self.driver.tap(trigger_pos[0], trigger_pos[1])
            return True
        # print("[*] Starting: Help alliance...")
        btn_help = os.path.join(ASSETS_DIR, 'help_btn.png')
        res = self.wait_and_click(btn_help, 0.1)
        if res:
            # print('Helped alliance')
            return True
        else:
            # print('No help found')
            return False

class GoToChatTask(BaseTask):
    def isChatPage(self):
        return self.check_exists(os.path.join(ASSETS_DIR, 'send_emoji_btn.png'))

    def scrollUp(self):
        if not self.isChatPage():
            return False

        self.driver.swipe(450, 400, 450, 1200, 900, 30)
        return True
    
    def run(self):
        if self.isChatPage(): return True
        chat_btn_pos = (400, 1500)
        print("[*] Starting: Go to chat...")
        
        self.driver.tap(chat_btn_pos[0], chat_btn_pos[1], jitter=3, sleep_time=0.3)
        time.sleep(0.5)
        self.wait_and_click(os.path.join(ASSETS_DIR, 'chat_alliance_btn.png'), timeout=6)
        if self.isChatPage():
            print("[+] Chat page opened.")
            return True
        else:
            return False
        
class SendChatFlowerTask(BaseTask):
    def run(self):
        go_to_chat_task = GoToChatTask(self.driver)
        if not go_to_chat_task.run():
            return False
        if self.check_exists(os.path.join(ASSETS_DIR, 'chat_alliance_btn.png'), threshold=0.8):
            if not self.wait_and_click(os.path.join(ASSETS_DIR, 'chat_alliance_btn.png'), timeout=1):
                print("[-] Failed to open alliance chat.")
                return False
        if self.wait_and_click(os.path.join(ASSETS_DIR, 'send_emoji_btn.png'), timeout=1):
            time.sleep(0.5)
            if self.wait_and_click(os.path.join(ASSETS_DIR, 'send_flower_emoji.png'), timeout=1):
                time.sleep(0.5)
                if self.wait_and_click(os.path.join(ASSETS_DIR, 'send_msg_btn.png'), timeout=1):
                    time.sleep(0.5)

                    print("[+] Flower sent successfully.")
                    self.wait_and_click(os.path.join(ASSETS_DIR, 'go_back_btn.png'), timeout=1)
                    return True
        return False
        
class ExitStuckStateTask(BaseTask):
    """Exit any stuck screen state.

    Performance note: detection uses a SINGLE screenshot — all templates are
    matched against the same frame and taps happen directly from it. Fresh
    screenshots are only taken when the screen changes (shop exit wait)."""

    def run(self, screen=None):
        self._raise_if_killed()
        if screen is None:
            screen = self.driver.screenshot()
        if screen is None:
            return False

        pos = self.matcher.find_template(screen, os.path.join(ASSETS_DIR, 'go_back_btn.png'), threshold=0.8)
        if pos:
            print("[*] Starting: Exit stuck state... [chat]")
            self.driver.tap(pos[0], pos[1])
            return True
        
        if (self.ocr_engine.check_text_exists(screen, '跳過')):
            print("[*] Starting: Exit stuck state... [story]")
            pos_skip_button = self.ocr_engine.get_text_position(screen, '跳過')
            self.driver.tap(int((pos_skip_button[0] + pos_skip_button[2])/2), int((pos_skip_button[1] + pos_skip_button[3])/2))
            return True
            
        # Healthy base view: dismiss the distance HUD if present
        pos_distance = self.matcher.find_template(screen, os.path.join(ASSETS_DIR, 'base_distance_btn.png'), threshold=0.8)
        if pos_distance:
            self.driver.tap(pos_distance[0], pos_distance[1])
            return True
    
        pos_dialog_continue = self.matcher.find_template(screen, os.path.join(ASSETS_DIR, 'dialog_continue_btn.png'), scan_area=(750, 1400, 880, 1580))
        if pos_dialog_continue:
            self.driver.tap(pos_dialog_continue[0], pos_dialog_continue[1])
            return True
        
        pos = self.matcher.find_template(screen, os.path.join(ASSETS_DIR, 'gather_location_confirm_frame.png'), threshold=0.8)
        if pos:
            print("[*] Starting: Exit stuck state... [gather]")
            pos_cancel = self.matcher.find_template(screen, os.path.join(ASSETS_DIR, 'gather_location_cancel_btn.png'), threshold=0.8)
            if pos_cancel:
                self.driver.tap(pos_cancel[0], pos_cancel[1])
                return True
            return False

        if (self.ocr_engine.check_text_exists(screen, '任意位置', scan_area=(300, 1400, 500, 1500))):
            print("[*] Starting: Exit stuck state... [teleport]")
            self.driver.tap(810, 1420)
            return True

        if (self.matcher.find_template(screen, os.path.join(ASSETS_DIR, 'base_btn.png'), threshold=0.92) is None
                and self.matcher.find_template(screen, os.path.join(ASSETS_DIR, 'world_btn.png'), threshold=0.92) is None):
            print("[*] Starting: Exit stuck state... [base]")
            pos_shop = self.matcher.find_template(screen, os.path.join(ASSETS_DIR, 'shop_btn.png'))
            if pos_shop:
                self.driver.tap(pos_shop[0], pos_shop[1])
                return self.wait_and_click(os.path.join(ASSETS_DIR, 'shop_exit_btn.png'), 1)
            return False
        return True

class GameLaunchTask(BaseTask):
    """Launch the game from the home screen if it isn't running yet."""
    def __init__(self, driver):
        super().__init__(driver)
        self.just_launched = False

    def run(self, screen=None):
        img = screen if screen is not None else self.driver.screenshot()
        if img is None:
            print('[-] Screenshot failed during game launch check')
            return False
        for game_icon in ['game_app_large.png', 'game_app_small.png']:
            game_icon_path = os.path.join(ASSETS_DIR, game_icon)
            game_icon_pos = self.matcher.find_template(img, game_icon_path)
            
            if game_icon_pos:
                print('Launching the game')
                self.driver.tap(game_icon_pos[0], game_icon_pos[1])
                while(not self.check_exists(os.path.join(ASSETS_DIR, 'world_btn.png'))):
                    time.sleep(5)
                self.just_launched = True
                return True

        if (not self.check_exists(os.path.join(ASSETS_DIR, 'world_btn.png')) and not self.check_exists(os.path.join(ASSETS_DIR, 'base_btn.png'))):
            print('[-] Game not running and no icon found')
            return False
        return True

class DigTask(BaseTask):
    """Digging task"""
    def __init__(self, driver, dig_strategy='check_and_tap'):
        super().__init__(driver)
        self.last_capture_id = None
        self.dig_strategy = dig_strategy
        self.capture_dump_dir = DUMP_DIR
        self.dig_detector = GameObjectDetector(os.path.join(MODEL_DIR, 'dig_model.onnx'))

    def determine_dig_type(self, img) -> DigType:
        res = self.dig_detector.detect(img)
        if len(res) == 0:
            return DigType.UN
        if res[0]['class_id'] == 0:
            return DigType.Drone
        elif res[0]['class_id'] == 1:
            return DigType.Excavator

    def navigate_to_dig_location(self) -> bool:
        """
        Open the chat and go to the dig location by tapping the shared location frame
        """
        # Open the chat page
        open_chat_Task = GoToChatTask(self.driver)
        res = open_chat_Task.run()
        if not res:
            self._notify('[Dig Task] Could not open chat page')
            self._photo_notify('Failed screen', self.driver.screenshot())
            return False
        # Find the share location frame
        tried_count = 0
        while(True):
            if tried_count == 20:
                self._notify('[Dig Task] failed to find location share frame')
                self._photo_notify('Failed screen', self.driver.screenshot())
                return False
            tried_count += 1
            pos_shared_click_res = self.wait_and_click(os.path.join(ASSETS_DIR, 'location_share_frame.png'), timeout=1)
            if pos_shared_click_res:
                time.sleep(0.5)
                img = self.driver.screenshot()
                if self.determine_dig_type(img) == DigType.UN:
                    return self.navigate_to_dig_location()
                self._notify('[Dig task] Navigated to the dig location')
                return True
            else:
                # The current page is already chat page, so there must be the shared location frame hidden in the history
                # First find if there is any boradcast notification taking the reading space
                if self.wait_and_click(os.path.join(ASSETS_DIR, 'notification_close_btn.jpg'), timeout=1):
                    # try one more time
                    continue
                # if still not found the share frame, scroll up the chat page to check for the location share information
                open_chat_Task.scrollUp()

    def go_to_dig(self):
        """
        This function is expected to call after navigation to the excavator
        """
        # detect exvactor
        img = self.driver.screenshot()
        dig_type = self.determine_dig_type(img)
        if dig_type == DigType.UN:
            if self.matcher.find_template(img, os.path.join(ASSETS_DIR, 'share_btn.png')) is not None:
                self._notify('[Dig Task] Already collected for this task')
                return False
            self._notify('[Dig Task] No dig object found in go_to_dig')
            self._photo_notify('Failed screen', self.driver.screenshot())

            return False
        self._notify(f'[Dig Task] Go to {'Excavator' if dig_type is DigType.Excavator else 'Drone'}')
        # the excavator is always in the centor
        self.driver.tap(450, 740, jitter=3, sleep_time=1)
        # sometimes the next scene loaded extremely slow...
        # while(not self.wait_and_click(os.path.join(ASSETS_DIR, 'dig_btn.png'), timeout=2) and not self.wait_and_click(os.path.join(ASSETS_DIR, 'fix_btn.png'), timeout=2)):
        dig_btn_pos = None
        tried_times = 0
        while(dig_btn_pos is None):
            if tried_times == 15:
                self._notify('[Dig Task] Stuck at sending out squad... Re-trying')
                self._photo_notify('Failed screen', self.driver.screenshot())

                return self.go_to_dig()
            tried_times += 1
            img = self.driver.screenshot()
            if dig_type == DigType.Excavator:
                dig_btn_pos = self.matcher.find_template(img, os.path.join(ASSETS_DIR, 'dig_btn.png'), threshold = 0.95, scan_area = (200, 800, 700, 1500))
            else:
                dig_btn_pos = self.matcher.find_template(img, os.path.join(ASSETS_DIR, 'fix_btn.png'), threshold = 0.95, scan_area = (200, 800, 700, 1500))
            time.sleep(0.3)

        self.driver.tap(dig_btn_pos[0], dig_btn_pos[1])

        # send the sqaud out, here we do not select team, but there must be one team available
        if not self.wait_and_click(os.path.join(ASSETS_DIR, 'send_out_btn.png'), timeout=5):
            self._notify('Could not send out Squad, please check if there is at lease 1 squad available')
            self._photo_notify('Failed screen', self.driver.screenshot())
            
            return False

        return True

    def get_counter_seconds(self):
        gift_scan_area = (370,600,510,770)

        current_frame = self.driver.screenshot()
        lower_white = np.array([240, 240, 245]) # BGR order
        upper_white = np.array([255, 255, 255])
        # there can be other players names overlapping the gift timer, but the color is different
        # the color of the gift timer is white, so we can use the color to filter out the other players names
        mask = cv2.inRange(current_frame, lower_white, upper_white)
        binary_img = cv2.bitwise_not(mask)
        txts = self.ocr_engine.extract_texts(binary_img, gift_scan_area)
        
        seconds = self.extract_digits_from_txts(txts)
        # if the dig has not started yet, wait for a while
        if len(txts) == 0 or seconds == -1:
            if self.determine_dig_type(current_frame) != DigType.UN:
                time.sleep(5)
                return self.get_counter_seconds()
            else:
                self._notify('[Dig Task] Cannot find the target')
                self._photo_notify('Failed screen', self.driver.screenshot())
                return -1
        return seconds


    def wait_and_collect_gift(self, pre_tap_times = 15):
        self._notify("[Dig Task] Waiting for gift to be available")
        gift_scan_area = (370,600,510,770)
        gift_name_scan_area = (320,800,660,870)
        if self.dig_strategy == 'pre_tap':
            while(True):
                seconds = self.get_counter_seconds()
                if seconds == -1:
                    return False

                elif seconds <= 5:
                    self._notify(f"[!] Pre-tapping {pre_tap_times} times before the gift is ready.")
                    if seconds > 1:
                        time.sleep(seconds - 1)
                    for i in range(pre_tap_times):
                        self.driver.tap(445, 730, jitter=2, sleep_time=0.1)
                    return True
                else:
                    time.sleep(4)                            
        else:
            cnt = 0                    
            while(not self.wait_and_click(os.path.join(ASSETS_DIR, 'gift_available.png'), timeout=5, interval=0.07, scan_area=gift_scan_area)):
                # Sometimes others collect the gift too fast that the share button will not be available, so that this loop may become deal lock
                if (cnt % 10 == 0):
                    img = self.driver.screenshot()
                    if self.matcher.find_template(img, os.path.join(ASSETS_DIR, 'share_btn.png'),  scan_area=gift_scan_area) is not None or self.determine_dig_type(img) == DigType.UN:
                        self._notify('[Dig Task] gift collected before able to collect')
                        save_capture(img, 'dig_capture', self.capture_dump_dir)
                        self._photo_notify('current frame', img)
                        return False
                cnt += 1
            time.sleep(0.5)
            return True

    def determine_result(self):
        img = self.driver.screenshot()
        if self.matcher.find_template(img, os.path.join(ASSETS_DIR, 'dig_result_double.png')) is not None or self.matcher.find_template(img, os.path.join(ASSETS_DIR, 'dig_result_normal.png')) is not None:
            self._notify('[Dig Task] Gift collected successfully')
            self.last_capture_id = save_capture(img)
            self.driver.press_back()
            time.sleep(0.3)
        else:
            self._notify('[Dig Task] Gift collect failed')
            self.last_capture_id = None
        img = self.driver.screenshot()

        close_btn_pos = self.matcher.find_template(img, os.path.join(ASSETS_DIR, 'dig_result_page_close_btn.png'), threshold=0.8, scan_area=(787, 144, 882, 248))
        if close_btn_pos is not None:
            self.driver.tap(close_btn_pos[0], close_btn_pos[1], jitter=1, sleep_time=0.1)
                                    
        share_location_close_btn_pos = self.matcher.find_template(img, os.path.join(ASSETS_DIR, 'share_location_close_btn.png'), threshold=0.8, scan_area=(776, 252, 874, 354))
        if share_location_close_btn_pos is not None:
            self.driver.tap(share_location_close_btn_pos[0], share_location_close_btn_pos[1], jitter=1, sleep_time=0.1)
        time.sleep(0.3)
        if self.last_capture_id == None:
            return False
        else:
            return True

    def gather_captures(self):
        """Take a bunch of screenshots for training idenfication models"""
        """Each call will take 2 screens"""
        for i in range(1):
            img = self.driver.screenshot()
            save_capture(img, 'dig_capture', self.capture_dump_dir)

    def extract_digits_from_txts(self, txts):
        cnt = 0
        res = -1
        for txt in txts:
            if txt.isdigit():
                cnt += 1
                res = int(txt)
            else:
                if txt.find(":") != -1:
                    # We directly return a large value here, because the time is still enough
                    return 60
                    # cnt += 1
                    # buf = txt.split(':')
                    # if len(buf) == 3:
                    #     res = 3600 * int(buf[0]) + 60 * int(buf[1]) + int(buf[2])
                    # elif len(buf) == 2:
                    #     res = 60 * int(buf[0]) + int(buf[1])

        if cnt == 1:
            return res
        else:
            return -1
    def run_new(self, trigger_pos=None):
        icon_dig = os.path.join(ASSETS_DIR, 'extravacator_notification.png')
        pos = trigger_pos if trigger_pos is not None else self.check_exists(icon_dig, threshold=0.8)
        if pos:
            self._notify("[*] Starting: Digging Task... - strategy: " + self.dig_strategy)

            self.driver.tap(pos[0], pos[1], jitter=3, sleep_time=0.3)
        if not self.navigate_to_dig_location():
            return False
        if not self.go_to_dig():
            return False
        if not self.wait_and_collect_gift():
            return False
        self.determine_result()
        send_chat_flower_task = SendChatFlowerTask(self.driver)
        send_chat_flower_task.run()
        return True
    def run(self, trigger_pos=None):
        return self.run_new(trigger_pos)
    def run_bk(self, trigger_pos=None):
        start_time = time.perf_counter()
        self._raise_if_killed()
        icon_dig = os.path.join(ASSETS_DIR, 'extravacator_notification.png')
        pos = trigger_pos if trigger_pos is not None else self.check_exists(icon_dig, threshold=0.8)
        if pos:
            self._notify("[*] Starting: Digging Task... - strategy: " + self.dig_strategy)

            self.driver.tap(pos[0], pos[1], jitter=3, sleep_time=0.3)
            # time.sleep(1)
            # Once clicked the notification, the screen change to the chat page, so we need to find and click the shared location
            # pos_shared_location = self.check_exists(os.path.join(ASSETS_DIR, 'location_share_frame.png'), threshold=0.8)
            # print(f"Shared location position: {pos_shared_location}")
            pos_shared_click_res = self.wait_and_click(os.path.join(ASSETS_DIR, 'location_share_frame.png'), timeout=5)
            if pos_shared_click_res:
                # self.driver.tap(pos_shared_location[0], pos_shared_location[1], jitter=3, sleep_time=0.3)
                # Need to wait till the next screen is loaded, otherwise the dig button will not be found
                while(self.check_exists(os.path.join(ASSETS_DIR, 'base_btn.png'), threshold=0.8) is None):
                    print("[*] Waiting for the dig button to appear...")
                    time.sleep(1)
                time.sleep(1)
                # self.gather_captures()
                # After clicking the shared location, the screen change to the world map with the extravacator at the center of the screen
                # Here hard code the position because the dig button is hard to match, and the extravacator is always at the center of the screen, so we can calculate the position of the dig button based on the center of the screen
                pos_dig_btn = (450, 740)
                self.driver.tap(pos_dig_btn[0], pos_dig_btn[1], jitter=3, sleep_time=0.3)
                # save_capture(self.driver.screenshot())
                # self.gather_captures()
                while(not self.wait_and_click(os.path.join(ASSETS_DIR, 'dig_btn.png'), timeout=2) and not self.wait_and_click(os.path.join(ASSETS_DIR, 'fix_btn.png'), timeout=2)):
                    exit_stuck_task = ExitStuckStateTask(self.driver)
                    if exit_stuck_task.run():
                        self._notify('⚠️ Stuck state detected and exited during dig task.')
                        time.sleep(0.5)
                        go_to_chat_task = GoToChatTask(self.driver)
                        if go_to_chat_task.run():
                            time.sleep(0.5)
                            self.wait_and_click(os.path.join(ASSETS_DIR, 'notification_close_btn.jpg'), timeout=1)
                            if self.wait_and_click(os.path.join(ASSETS_DIR, 'location_share_frame.png'), timeout=2):
                                time.sleep(1)
                                self.driver.tap(pos_dig_btn[0], pos_dig_btn[1], jitter=3, sleep_time=0.3)
                            else:
                                save_capture(self.driver.screenshot())
                                self.wait_and_click(os.path.join(ASSETS_DIR, 'go_back_btn.png'), timeout=2)
                                self._notify('⚠️ Stuck state detected and recovery failed during dig task.')
                                return False
                        else:
                            save_capture(self.driver.screenshot())
                            self._notify('⚠️ Stuck state detected and recovery failed during dig task.')
                            return False

                    else:
                        self._notify('⚠️ Stuck state detected and recovery failed during dig task.')
                        return False
                    

                self.wait_and_click(os.path.join(ASSETS_DIR, 'send_out_btn.png'), timeout=5)
                # Wait for the dig action to complete
                cnt = 1
                gift_collected = False
                gift_scan_area = (370,600,510,770)
                gift_name_scan_area = (320,800,660,870)
                if self.dig_strategy == 'pre_tap':
                    pre_tap_times = 15
                    while(not gift_collected):
                        current_frame = self.driver.screenshot()
                        lower_white = np.array([240, 240, 245]) # BGR order
                        upper_white = np.array([255, 255, 255])
                        # there can be other players names overlapping the gift timer, but the color is different
                        # the color of the gift timer is white, so we can use the color to filter out the other players names
                        mask = cv2.inRange(current_frame, lower_white, upper_white)
                        binary_img = cv2.bitwise_not(mask)
                        txts = self.ocr_engine.extract_texts(binary_img, gift_scan_area)
                        # self.gather_captures()
                        seconds = self.extract_digits_from_txts(txts)
                        if len(txts) == 0 or seconds == -1:
                            current_time = time.perf_counter()
                            time_elapsed = current_time - start_time
                            if time_elapsed <= 30:
                                time.sleep(5)
                                continue
                            else:
                                break
                        
                        if seconds <= 5 and seconds != -1:
                            self._notify(f"[!] Pre-tapping {pre_tap_times} times before the gift is ready.")
                            if seconds > 1:
                                time.sleep(seconds - 1)
                            for i in range(pre_tap_times):
                                self.driver.tap(445, 730, jitter=2, sleep_time=0.1)
                            current_frame = self.driver.screenshot()
                            close_btn_pos = self.matcher.find_template(current_frame, os.path.join(ASSETS_DIR, 'dig_result_page_close_btn.png'), threshold=0.8, scan_area=(787, 144, 882, 248))
                            if close_btn_pos:
                                self.last_capture_id = save_capture(self.driver.screenshot())
                                self.driver.tap(close_btn_pos[0], close_btn_pos[1], jitter=1, sleep_time=0.1)
                                gift_collected = True
                                break
                            share_location_close_btn_pos = self.matcher.find_template(current_frame, os.path.join(ASSETS_DIR, 'share_location_close_btn.png'), threshold=0.8, scan_area=(776, 252, 874, 354))
                            if share_location_close_btn_pos:
                                self._notify("Collected gift but not sure the collected one, because pre-tap opened the shared location page")
                                self.driver.tap(share_location_close_btn_pos[0], share_location_close_btn_pos[1], jitter=1, sleep_time=0.1)
                                self.last_capture_id = save_capture(self.driver.screenshot())
                                gift_collected = True
                                break
                        time.sleep(4)
                        
                else:                        
                    while(not self.wait_and_click(os.path.join(ASSETS_DIR, 'gift_available.png'), timeout=5, interval=0.07, scan_area=gift_scan_area)):
                        # Sometimes others collect the gift too fast that the share button will not be available, so that this loop may become deal lock
                        # self.gather_captures()
                        if (cnt % 10 == 0 and (self.check_exists(os.path.join(ASSETS_DIR, 'share_btn.png'), scan_area=gift_scan_area) or (not self.check_text_exists("挖掘點", scan_area=gift_name_scan_area) and not self.check_text_exists("實驗無人機", scan_area=gift_name_scan_area)))):
                            gift_collected = False
                            break
                        cnt += 1
                if gift_collected:
                    self._notify("[+] Gift collected.")
                time.sleep(0.5)
                # Save the reward screen for the activity log
                if self.dig_strategy != 'pre_tap':
                    self.last_capture_id = save_capture(self.driver.screenshot())
                # Exit gift page
                # self.driver.tap(450, 1300, jitter=3, sleep_time=0.3)
                if gift_collected and self.dig_strategy != 'pre_tap':
                    self.driver.press_back()
                    time.sleep(0.5)
                    send_chat_flower_task = SendChatFlowerTask(self.driver)
                    send_chat_flower_task.run()
                    time.sleep(0.5)
                # self.wait_and_click(os.path.join(ASSETS_DIR, 'base_btn.png'), timeout=5)
                return True

        return False

class TestTask(BaseTask):
    """Test task for debugging purposes"""
    def run(self):
        print("[*] Starting: Test Task...")
        # Implement test logic here
        self.driver.press_back()
        return True

class LuckyGiftTask(BaseTask):
    def __init__(self, driver):
        super().__init__(driver)
        self.last_capture_id = None

    def run(self, trigger_pos=None):
        self._raise_if_killed()
        # print("[*] Starting: Help alliance...")
        if trigger_pos is not None:
            self.driver.tap(trigger_pos[0], trigger_pos[1])
            lucky_gift_notification_res = True
        else:
            lucky_gift_notification_res = self.wait_and_click(os.path.join(ASSETS_DIR, 'lucky_gift_notification.png'), 0.1)
        if lucky_gift_notification_res:
            self._notify('[*] Started collecting Lucky gift')
            shared_click_res = self.wait_and_click(os.path.join(ASSETS_DIR, 'lucky_gift_share_frame.png'), timeout=5)
            if shared_click_res:
                open_click_res = self.wait_and_click(os.path.join(ASSETS_DIR, 'gift_open_btn.png'), timeout=5)
                if open_click_res:
                    # The gift is already opened — like if the button is there,
                    # but capture and record even if it isn't.
                    self.wait_and_click(os.path.join(ASSETS_DIR, 'like_btn.png'), timeout=2)
                    self.last_capture_id = save_capture(self.driver.screenshot(), prefix='lucky_gift')
                    self.wait_and_click(os.path.join(ASSETS_DIR, 'lucky_gift_list_exit.jpg'), timeout=2)
                    self.wait_and_click(os.path.join(ASSETS_DIR, 'go_back_btn.png'), timeout=2)
                    self._notify('[+] Lucky gift collected.')
                    return True
        return False

class JoinRallyTask(BaseTask):
    def __init__(self, driver, rally_preference = None):
        super().__init__(driver)
        self._rally_preference = rally_preference
        self.last_join_info = None

    def analyze_rally_info(self):
        frames = [30, 225, 862, 615, 36, 644, 860, 1025]
        # get the info of the first rally
        res = []
        for i in range(2):
            tried_count = 0
            ocr_res = []
            monster_type = MonsterType.UN
            monster_level = 0
            team_lead = ''
            while(True):
                if tried_count == 20:
                    return []
                tried_count += 1
                screen = self.driver.screenshot()
            
                #['攻擊', '[DGET]东方虎3', '集結中...', '00:00:59', 'Lv.26', '末日精英', '單位/上限[1/5]', '距離12公里']
                ocr_res = self.ocr_engine.extract_texts(screen, frames[4*i:4*(i+1)])
                if len(ocr_res) == 0:
                    break
                for txt in ocr_res:
                    if '末日精英' in txt:
                        monster_type = MonsterType.DE
                    elif '末日遊蕩者' in txt:
                        monster_type = MonsterType.DW
                    elif '喪屍首領' in txt:
                        monster_type = MonsterType.ZB
                
                for txt in ocr_res:
                    if 'Lv' in txt:
                        try:
                            monster_level = int(txt[3:])
                        except ValueError:
                            print('[Analyze rally info] parsing level error')
                            continue

                if monster_level != 0 and monster_type != MonsterType.UN:
                    team_lead = ocr_res[1]
                    match_res = self.matcher.find_template(screen, os.path.join(ASSETS_DIR, 'join_party_btn.png'), scan_area=frames[4*i:4*(i+1)])
                    if match_res:
                        res.append((monster_type, monster_level, True, team_lead))
                    else:
                        res.append((monster_type, monster_level, False, team_lead))
                    break
                time.sleep(0.3)
                
        return res

    def run(self, trigger_pos=None):
        self._raise_if_killed()
        # Manual /run rally: look for the notification ourselves; the engine's
        # cycle passes the position it already found (same scan area).
        if trigger_pos is None:
            trigger_pos = self.check_exists(os.path.join(ASSETS_DIR, 'party_notification_btn.png'),
                                            threshold=0.8, scan_area=(770, 966, 872, 1072))
        if trigger_pos is None:
            return False

        first_rally_pos = (460, 460)
        second_rally_pos = (460, 870)
        rally_join_btns = [first_rally_pos, second_rally_pos]
        # self._notify('[*] Checking Rallies...')
        self.driver.tap(trigger_pos[0], trigger_pos[1])
        time.sleep(0.5)
        analyze_rally_res = self.analyze_rally_info()
        current_target = -1
        join_whitelist = False
        for i in range(len(analyze_rally_res)):
            # self._notify(f'Found {analyze_rally_res[i][0].value}, {analyze_rally_res[i][1]}, {"Joinable" if analyze_rally_res[i][2] else "Full"}')
            if join_whitelist:
                break
            if analyze_rally_res[i][0] is MonsterType.DE and analyze_rally_res[i][2]:
                for pref in self._rally_preference:
                    if pref['name'] == 'DE' and pref['enabled']:
                        if current_target != -1:
                            if analyze_rally_res[current_target][0] is MonsterType.DE:
                                if analyze_rally_res[i][1] <= pref['level'] and analyze_rally_res[i][1] > analyze_rally_res[current_target][1]:
                                    current_target = i
                        else:
                            current_target = i
            elif analyze_rally_res[i][0] is MonsterType.DW and analyze_rally_res[i][2]:
                for pref in self._rally_preference:
                    if pref['name'] == 'DW' and pref['enabled']:
                        if current_target != -1:
                            if analyze_rally_res[current_target][0] is MonsterType.DW:
                                if analyze_rally_res[i][1] <= pref['level'] and analyze_rally_res[i][1] > analyze_rally_res[current_target][1]:
                                    current_target = i
                            elif analyze_rally_res[current_target][0] is MonsterType.DE:
                                if analyze_rally_res[i][1] <= pref['level']:
                                    current_target = i
                        else:
                            if analyze_rally_res[i][1] <= pref['level']:
                                current_target = i
            elif analyze_rally_res[i][0] is MonsterType.ZB and analyze_rally_res[i][2]:
                for pref in self._rally_preference:
                    if pref['name'] == 'ZB' and pref['enabled']:
                        if pref['whitelist'] is not None:
                            for name in pref['whitelist']:
                                if name in analyze_rally_res[i][3]:
                                    join_whitelist = True
                                    current_target = i
                        if join_whitelist:
                            break
                        if current_target != -1:
                            if analyze_rally_res[current_target][0] is MonsterType.ZB:
                                if analyze_rally_res[i][1] <= pref['level'] and analyze_rally_res[i][1] > analyze_rally_res[current_target][1]:
                                    current_target = i
                            else:
                                if analyze_rally_res[i][1] <= pref['level']:
                                    current_target = i
                        else:
                            if analyze_rally_res[i][1] <= pref['level']:
                                current_target = i
            
        if current_target != -1:
            self.driver.tap(rally_join_btns[current_target][0], rally_join_btns[current_target][1])
            
            if self.wait_and_click(os.path.join(ASSETS_DIR, 'send_out_btn.png'), timeout=5):
                monster = analyze_rally_res[current_target]
                self.last_join_info = f'{monster[0].value} Lv.{monster[1]}'
                self._notify(f'Joining rally: {monster[0].value}, Lv.{monster[1]}, lead: {monster[3]}')
                return monster
            else:
                screen_tap_join = self.driver.screenshot()
                if self.ocr_engine.check_text_exists(screen_tap_join, '名片', (200, 0, 350, 100)):
                    # the rally is full before able to join, need to exit here
                    self.driver.tap(850, 25)
                    time.sleep(0.3)
                    self.driver.tap(50, 1500)
                return False
        self.wait_and_click(os.path.join(ASSETS_DIR, 'go_back_btn.png'), timeout=2)
        return False

class CongratulationsTask(BaseTask):
    """When members' base is upgraded, need to collect the congratulation gift"""
    def run(self, trigger_pos=None):
        self._raise_if_killed()
        if trigger_pos is not None:
            self.driver.tap(trigger_pos[0], trigger_pos[1])
        else:
            congrats_notification_pos = self.check_exists(os.path.join(ASSETS_DIR, 'congrats_notification.png'), threshold=0.8, scan_area=(600,1300,750,1480))
            if congrats_notification_pos:
                self.driver.tap(congrats_notification_pos[0], congrats_notification_pos[1])
            else:
                return False
        
        res = self.wait_and_click(os.path.join(ASSETS_DIR, 'congrats_btn.png'), timeout=5)
        if res:
            # print('Helped alliance')
            self._notify("[+] Congratulations gift collected.")
            return True
        else:
            return False