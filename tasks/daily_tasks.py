# -*- coding: utf-8 -*-
import os
import time
from tasks.base_task import BaseTask
from config import ASSETS_DIR
from core.logger import save_capture
from enum import Enum

class MonsterType(Enum):
    DE = 'Doom Elite'
    DW = 'Doom Walker'
    ZB = 'Zombie'
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

    def run(self, screen=None):
        img = screen if screen is not None else self.driver.screenshot()
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

class DigTask(BaseTask):
    """Digging task"""
    def __init__(self, driver):
        super().__init__(driver)
        self.last_capture_id = None

    def run(self, trigger_pos=None):
        self._raise_if_killed()
        icon_dig = os.path.join(ASSETS_DIR, 'extravacator_notification.png')
        pos = trigger_pos if trigger_pos is not None else self.check_exists(icon_dig, threshold=0.8)
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
                pos_dig_btn = (450, 740)
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
                gift_scan_area = (370,620,510,770)
                gift_name_scan_area = (320,800,660,870)
                while(not self.wait_and_click(os.path.join(ASSETS_DIR, 'gift_available.png'), timeout=5, interval=0.7, scan_area=gift_scan_area)):
                    # Sometimes others collect the gift too fast that the share button will not be available, so that this loop may become deal lock
                    if (cnt % 10 == 0 and (self.check_exists(os.path.join(ASSETS_DIR, 'share_btn.png'), scan_area=gift_scan_area) or (not self.check_text_exists("挖掘點", scan_area=gift_name_scan_area) and not self.check_text_exists("實驗無人機", scan_area=gift_name_scan_area)))):
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
    def __init__(self, driver, rally_preference):
        super().__init__(driver)
        self._rally_preference = rally_preference
        self.last_join_info = None

    def analyze_rally_info(self):
        frames = [30, 225, 862, 615, 36, 644, 860, 1025]
        screen = self.driver.screenshot()
        # get the info of the first rally
        res = []
        for i in range(2):
            #['攻擊', '[DGET]东方虎3', '集結中...', '00:00:59', 'Lv.26', '末日精英', '單位/上限[1/5]', '距離12公里']
            ocr_res = self.ocr_engine.extract_texts(screen, frames[4*i:4*(i+1)])
            
            monster_type = MonsterType.UN
            monster_level = 0
            
            for txt in ocr_res:
                if '末日精英' in txt:
                    monster_type = MonsterType.DE
                elif '末日遊蕩者' in txt:
                    monster_type = MonsterType.DW
                elif '喪屍首領' in txt:
                    monster_type = MonsterType.ZB
            for txt in ocr_res:
                if 'Lv' in txt:
                    monster_level = int(txt[3:])
            if monster_level != 0:
                match_res = self.matcher.find_template(screen, os.path.join(ASSETS_DIR, 'join_party_btn.png'), scan_area=frames[4*i:4*(i+1)])
                if match_res:
                    res.append((monster_type, monster_level, True))
                else:
                    res.append((monster_type, monster_level, False))
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

        for i in range(len(analyze_rally_res)):
            # self._notify(f'Found {analyze_rally_res[i][0].value}, {analyze_rally_res[i][1]}, {"Joinable" if analyze_rally_res[i][2] else "Full"}')

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
            screen_tap_join = self.driver.screenshot()
            if self.ocr_engine.check_text_exists(screen_tap_join, '名片', (200, 0, 350, 100)):
                # the rally is full before able to join, need to exit here
                self.driver.tap(850, 25)
                time.sleep(0.3)
                self.driver.tap(50, 1500)
                return False
            if self.wait_and_click(os.path.join(ASSETS_DIR, 'send_out_btn.png'), timeout=5):
                monster = analyze_rally_res[current_target]
                self.last_join_info = f'{monster[0].value} Lv.{monster[1]}'
                self._notify(f'Joining rally: {monster[0].value}, Lv.{monster[1]}')
                return monster
            else:
                return False
        self.wait_and_click(os.path.join(ASSETS_DIR, 'go_back_btn.png'), timeout=2)
        return False
