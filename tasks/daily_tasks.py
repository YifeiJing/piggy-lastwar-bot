# -*- coding: utf-8 -*-
import os
import time
from tasks.base_task import BaseTask
from config import ASSETS_DIR
from core.logger import save_capture

class AllianceHelpTask(BaseTask):
    def run(self):
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
    def run(self):
        chat_btn_pos = (400, 1500)
        print("[*] Starting: Go to chat...")
        self.driver.tap(chat_btn_pos[0], chat_btn_pos[1], jitter=3, sleep_time=0.3)
        time.sleep(0.5)
        if self.check_exists(os.path.join(ASSETS_DIR, 'go_back_btn.png'), threshold=0.8):
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

    def run(self):
        self._raise_if_killed()
        screen = self.driver.screenshot()
        if screen is None:
            return False

        pos = self.matcher.find_template(screen, os.path.join(ASSETS_DIR, 'go_back_btn.png'), threshold=0.8)
        if pos:
            print("[*] Starting: Exit stuck state... [chat]")
            self.driver.tap(pos[0], pos[1])
            return True

        pos = self.matcher.find_template(screen, os.path.join(ASSETS_DIR, 'gather_location_confirm_frame.png'), threshold=0.8)
        if pos:
            print("[*] Starting: Exit stuck state... [gather]")
            pos_cancel = self.matcher.find_template(screen, os.path.join(ASSETS_DIR, 'gather_location_cancel_btn.png'), threshold=0.8)
            if pos_cancel:
                self.driver.tap(pos_cancel[0], pos_cancel[1])
                return True
            return False

        if (self.matcher.find_template(screen, os.path.join(ASSETS_DIR, 'base_btn.png'), threshold=0.8) is None
                and self.matcher.find_template(screen, os.path.join(ASSETS_DIR, 'world_btn.png'), threshold=0.8) is None):
            print("[*] Starting: Exit stuck state... [base]")
            pos_shop = self.matcher.find_template(screen, os.path.join(ASSETS_DIR, 'shop_btn.png'))
            if pos_shop:
                self.driver.tap(pos_shop[0], pos_shop[1])
                return self.wait_and_click(os.path.join(ASSETS_DIR, 'shop_exit_btn.png'), 1)
            return False

        # Healthy base view: dismiss the distance HUD if present
        pos_distance = self.matcher.find_template(screen, os.path.join(ASSETS_DIR, 'base_distance_btn.png'), threshold=0.8)
        if pos_distance:
            self.driver.tap(pos_distance[0], pos_distance[1])
        return True

class GameLaunchTask(BaseTask):
    """Launch the game from the home screen if it isn't running yet."""
    def __init__(self, driver):
        super().__init__(driver)
        self.just_launched = False

    def run(self):
        img = self.driver.screenshot()
        if img is None:
            print('[-] Screenshot failed during game launch check')
            return False

        height, width, channels = img.shape
        if height == 1600 and width == 900:
            # Game already launched
            return True
        else:
            print('Launching the game')
            pos = self.matcher.find_template(img, os.path.join(ASSETS_DIR, 'game_app.png'))
            if pos:
                self.driver.tap(pos[0], pos[1])
                self.just_launched = True
                return True
            else:
                print('Cannot find the game icon')
                return False

class AllianceDonationTask(BaseTask):
    """Alliance tech donation automation task"""
    def run(self):
        print("[*] Starting: Alliance Donation Task...")
        btn_alliance = os.path.join(ASSETS_DIR, 'btn_alliance.png')
        btn_tech = os.path.join(ASSETS_DIR, 'btn_tech.png')
        btn_donate = os.path.join(ASSETS_DIR, 'btn_donate.png')

        # 1. Locate alliance button
        if not self.wait_and_click(btn_alliance, timeout=5):
            print("[-] Alliance button not found, skipping task.")
            return False

        # 2. Enter tech tree
        if not self.wait_and_click(btn_tech, timeout=5):
            print("[-] Tech tree button not found.")
            self.driver.press_back()
            return False

        # 3. Donate loop
        print("[*] Executing donation click sequence...")
        donated_count = 0
        for _ in range(25):
            screen = self.driver.screenshot()
            pos = self.matcher.find_template(screen, btn_donate, threshold=0.8)
            if not pos:
                break
            self.driver.tap(pos[0], pos[1], jitter=2, sleep_time=0.25)
            donated_count += 1

        print(f"[+] Donation complete. Executed {donated_count} clicks.")
        self.driver.press_back()
        time.sleep(0.5)
        self.driver.press_back()
        return True


class CollectResourcesTask(BaseTask):
    """Base harvesting task"""
    def run(self):
        print("[*] Starting: Resource Collection Task...")
        icon_food = os.path.join(ASSETS_DIR, 'icon_harvest_food.png')
        icon_iron = os.path.join(ASSETS_DIR, 'icon_harvest_iron.png')
        icon_gold = os.path.join(ASSETS_DIR, 'icon_harvest_gold.png')

        for icon in [icon_food, icon_iron, icon_gold]:
            if os.path.exists(icon):
                screen = self.driver.screenshot()
                pts = self.matcher.find_all_templates(screen, icon, threshold=0.8)
                for pt in pts:
                    self.driver.tap(pt[0], pt[1], jitter=3, sleep_time=0.3)
        print("[+] Resource collection finished.")
        return True

class DigTask(BaseTask):
    """Digging task"""
    def __init__(self, driver):
        super().__init__(driver)
        self.last_capture_id = None

    def run(self):
        icon_dig = os.path.join(ASSETS_DIR, 'extravacator_notification.png')
        pos = self.check_exists(icon_dig, threshold=0.8)
        if pos:
            self._notify("[*] Starting: Digging Task...")

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
                # After clicking the shared location, the screen change to the world map with the extravacator at the center of the screen
                # Here hard code the position because the dig button is hard to match, and the extravacator is always at the center of the screen, so we can calculate the position of the dig button based on the center of the screen
                pos_dig_btn = (450, 700)
                self.driver.tap(pos_dig_btn[0], pos_dig_btn[1], jitter=3, sleep_time=0.3)
                # save_capture(self.driver.screenshot())
                while(not self.wait_and_click(os.path.join(ASSETS_DIR, 'dig_btn.png'), timeout=1) and not self.wait_and_click(os.path.join(ASSETS_DIR, 'fix_btn.png'), timeout=1)):
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
                gift_collected = True
                while(not self.wait_and_click(os.path.join(ASSETS_DIR, 'gift_available.png'), timeout=5, interval=0.35)):
                    # Sometimes others collect the gift too fast that the share button will not be available, so that this loop may become deal lock
                    if (cnt % 10 == 0 and (self.check_exists(os.path.join(ASSETS_DIR, 'share_btn.png')) or (not self.check_text_exists("挖掘點") and not self.check_text_exists("實驗無人機")))):
                        gift_collected = False
                        break
                    cnt += 1
                    # time.sleep(0.1)
                if gift_collected:
                    self._notify("[+] Gift collected.")
                time.sleep(0.5)
                # Save the reward screen for the activity log
                self.last_capture_id = save_capture(self.driver.screenshot())
                # Exit gift page
                # self.driver.tap(450, 1300, jitter=3, sleep_time=0.3)
                if gift_collected:
                    self.driver.press_back()
                    time.sleep(0.5)
                    send_chat_flower_task = SendChatFlowerTask(self.driver)
                    send_chat_flower_task.run()
                    time.sleep(0.5)
                self.wait_and_click(os.path.join(ASSETS_DIR, 'base_btn.png'), timeout=5)
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

    def run(self):
        # print("[*] Starting: Help alliance...")
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

class JoinDETask(BaseTask):
    """Join the DE alliance if not already a member."""
    def run(self):
        print("[*] Starting: Join DE Alliance Task...")
        btn_alliance = os.path.join(ASSETS_DIR, 'rally_available_notification.png')
        btn_join_de = os.path.join(ASSETS_DIR, 'btn_join_de.png')

        # 1. Locate alliance button
        if not self.wait_and_click(btn_alliance, timeout=5):
            print("[-] Alliance button not found, skipping task.")
            return False

        # 2. Join DE alliance
        if not self.wait_and_click(btn_join_de, timeout=5):
            print("[-] Join DE button not found or already a member.")
            self.driver.press_back()
            return False

        print("[+] Successfully joined DE alliance.")
        self.driver.press_back()
        return True