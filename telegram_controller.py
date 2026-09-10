# -*- coding: utf-8 -*-
import asyncio
import os
from io import BytesIO

import cv2
from telegram import Update
from telegram.ext import Application, MessageHandler, filters

from config import DIG_CAPTURE_DIR, TELEGRAM_ALLOWED_CHATS, TELEGRAM_BOT_TOKEN
from core.engine import TASK_MAP
from core.logger import save_capture


class TelegramController:
    """Telegram remote control: commands either mutate engine state directly
    (instant) or are queued for the engine thread (/run). Manual taps/swipes
    execute directly under the driver lock."""

    def __init__(self, engine, driver):
        self.engine = engine
        self.driver = driver
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self._loop = None

    def run(self):
        if not TELEGRAM_ALLOWED_CHATS:
            print('[!] TELEGRAM_ALLOWED_CHATS is empty — send any message to the bot to learn your chat id.')
        self.application.add_handler(MessageHandler(filters.TEXT, self._on_message))
        print('[*] Telegram controller started, polling...')
        try:
            asyncio.run(self._run())
        except KeyboardInterrupt:
            print('[*] Telegram controller stopped.')
        finally:
            self.engine.exit_event.set()

    async def _run(self):
        self._loop = asyncio.get_running_loop()
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        try:
            await asyncio.Event().wait()  # poll forever until Ctrl+C
        finally:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            self._loop = None

    def send_message(self, text: str):
        """Called from the engine thread to push async events to the user."""
        if self._loop is None:
            print(f'[TG] (not sent, bot not ready): {text}')
            return
        for chat_id in TELEGRAM_ALLOWED_CHATS:
            future = asyncio.run_coroutine_threadsafe(
                self.application.bot.send_message(chat_id=chat_id, text=text), self._loop)
            future.add_done_callback(_log_send_result)

    def help_text(self) -> str:
        return (
            '📖 Commands:\n'
            '/status — engine state + screenshot\n'
            '/screenshot — current screen\n'
            '/capture [prefix] — save current screen to dig_captures/\n'
            '/ocr [text] — recognize screen text / check if text is on screen\n'
            f"/run <task> — run once: {', '.join(TASK_MAP)}\n"
            '/pause — pause the auto loop\n'
            '/resume — resume the auto loop\n'
            '/kill — abort the running task (dead-loop rescue)\n'
            '/stop — stop the auto loop\n'
            '/start — start/resume the auto loop\n'
            '/stats — today\'s counters\n'
            '/report — stats + screenshot\n'
            '/history [n] — last N records (text only)\n'
            '/record <id> — one record + its capture image\n'
            '/tap <x> <y> — tap the screen\n'
            '/swipe <x1> <y1> <x2> <y2> [ms] — swipe\n'
            '/back — Android back button\n'
            '/help — this text'
        )

    # ---- message handling (async handlers, PTB v21) ----

    async def _on_message(self, update: Update, context):
        msg = update.effective_message
        if msg is None or msg.text is None:
            return
        chat = update.effective_chat
        if chat is None:
            return

        if chat.id not in TELEGRAM_ALLOWED_CHATS:
            await msg.reply_text(
                f'⛔ Unauthorized. Your chat id: {chat.id}\n'
                'Add it to TELEGRAM_ALLOWED_CHATS in config.py to gain control.')
            return

        text = msg.text
        if not text.startswith('/'):
            await msg.reply_text(self.help_text())
            return

        parts = text.split()
        cmd = parts[0].split('@')[0].lower()
        args = parts[1:]
        await self._dispatch(cmd, args, msg, chat.id)

    async def _dispatch(self, cmd: str, args: list, msg, chat_id: int):
        if cmd == '/start':
            self.engine.start_loop()
        elif cmd == '/help':
            await msg.reply_text(self.help_text())
        elif cmd == '/status':
            await msg.reply_text(f'📊 Engine: {self.engine.status}\n{self.engine.stats.format_stats()}')
            if not await self._send_screenshot(chat_id):
                await msg.reply_text('❌ Screenshot failed (device not reachable?)')
        elif cmd == '/screenshot':
            if not await self._send_screenshot(chat_id):
                await msg.reply_text('❌ Screenshot failed (device not reachable?)')
        elif cmd == '/capture':
            prefix = ''.join(c for c in args[0] if c.isalnum() or c == '_') if args else 'manual'
            if not prefix:
                prefix = 'manual'
            await self._save_capture(chat_id, prefix)
        elif cmd == '/ocr':
            if args:
                await self._check_text(chat_id, ' '.join(args))
            else:
                await self._recognize_text(chat_id)
        elif cmd == '/stats':
            await msg.reply_text(self.engine.stats.format_stats())
        elif cmd == '/report':
            await msg.reply_text(f'📊 Engine: {self.engine.status}\n{self.engine.stats.format_stats()}')
            if not await self._send_screenshot(chat_id):
                await msg.reply_text('❌ Screenshot failed (device not reachable?)')
        elif cmd == '/history':
            try:
                n = int(args[0]) if args else 10
            except ValueError:
                await msg.reply_text('Usage: /history [n] (1-20)')
                return
            await self._send_history(chat_id, max(1, n))
        elif cmd == '/record':
            try:
                record_id = int(args[0])
            except (ValueError, IndexError):
                await msg.reply_text('Usage: /record <id> — id from /history')
                return
            await self._send_record(chat_id, record_id)
        elif cmd == '/run':
            if not args:
                await msg.reply_text(f"Usage: /run <task>. Available: {', '.join(TASK_MAP)}")
                return
            self.engine.run_task(args[0].lower())
        elif cmd == '/pause':
            self.engine.pause()
        elif cmd == '/resume':
            self.engine.resume()
        elif cmd == '/stop':
            self.engine.stop_loop()
        elif cmd == '/kill':
            self.engine.kill_task()
        elif cmd == '/tap':
            try:
                x, y = int(args[0]), int(args[1])
            except (ValueError, IndexError):
                await msg.reply_text('Usage: /tap <x> <y>')
                return
            self.driver.tap(x, y)
            await msg.reply_text(f'✅ Tapped ({x}, {y})')
        elif cmd == '/swipe':
            try:
                x1, y1, x2, y2 = (int(a) for a in args[:4])
                duration = int(args[4]) if len(args) > 4 else 350
            except (ValueError, IndexError):
                await msg.reply_text('Usage: /swipe <x1> <y1> <x2> <y2> [duration_ms]')
                return
            self.driver.swipe(x1, y1, x2, y2, duration)
            await msg.reply_text(f'✅ Swiped ({x1},{y1}) -> ({x2},{y2})')
        elif cmd == '/back':
            self.driver.press_back()
            await msg.reply_text('✅ Back pressed')
        else:
            await msg.reply_text(f'❓ Unknown command.\n{self.help_text()}')

    async def _send_screenshot(self, chat_id: int) -> bool:
        img = await asyncio.to_thread(self.driver.screenshot)
        if img is None:
            return False
        ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return False
        await self.application.bot.send_photo(chat_id=chat_id, photo=BytesIO(buf.tobytes()))
        return True

    async def _save_capture(self, chat_id: int, prefix: str) -> bool:
        """Save the current screen into dig_captures/ without sending it."""
        img = await asyncio.to_thread(self.driver.screenshot)
        file_name = save_capture(img, prefix=prefix, capture_dir=DIG_CAPTURE_DIR)
        if file_name:
            await self.application.bot.send_message(
                chat_id=chat_id, text=f'💾 Saved {file_name} to dig_captures/.')
            return True
        await self.application.bot.send_message(
            chat_id=chat_id, text='❌ Screenshot failed (device not reachable?)')
        return False

    async def _recognize_text(self, chat_id: int):
        """OCR the current screen and send all recognized text fragments."""
        img = await asyncio.to_thread(self.driver.screenshot)
        if img is None:
            await self.application.bot.send_message(
                chat_id=chat_id, text='❌ Screenshot failed (device not reachable?)')
            return
        # OCR takes a couple of seconds — keep it off the event loop too.
        texts = await asyncio.to_thread(self.engine.ocr_engine.extract_texts, img)
        if not texts:
            await self.application.bot.send_message(chat_id=chat_id, text='🔤 No text recognized.')
            return
        joined = ' | '.join(texts)
        if len(joined) > 3000:
            joined = joined[:3000] + '…'
        await self.application.bot.send_message(chat_id=chat_id, text=f'🔤 Recognized:\n{joined}')

    async def _check_text(self, chat_id: int, target: str):
        """Check whether target text is visible on the current screen."""
        img = await asyncio.to_thread(self.driver.screenshot)
        if img is None:
            await self.application.bot.send_message(
                chat_id=chat_id, text='❌ Screenshot failed (device not reachable?)')
            return
        found = await asyncio.to_thread(self.engine.ocr_engine.check_text_exists, img, target)
        if found:
            await self.application.bot.send_message(
                chat_id=chat_id, text=f"✅ Found '{target}' on screen.")
        else:
            await self.application.bot.send_message(
                chat_id=chat_id, text=f"❌ '{target}' not found on screen.")

    async def _send_history(self, chat_id: int, limit: int):
        """Send the last N activity records as text (no images)."""
        records = self.engine.logger.fetch_all(limit=limit)
        bot = self.application.bot
        if not records:
            await bot.send_message(chat_id=chat_id, text='📋 No records yet.')
            return

        lines = [f'📋 Last {len(records)} records:']
        for r in records:
            line = f"{r['id']}. [{r['time']}] {r['event']}"
            if r['capture']:
                line += f" — {r['capture']}"
            lines.append(line)
        await bot.send_message(chat_id=chat_id, text='\n'.join(lines))

    async def _send_record(self, chat_id: int, record_id: int):
        """Checkout one record; includes its capture image if it has one."""
        bot = self.application.bot
        record = self.engine.logger.fetch_by_id(record_id)
        if record is None:
            await bot.send_message(chat_id=chat_id, text=f'❌ No record with id {record_id}.')
            return

        line = f"#{record['id']} [{record['time']}] {record['event']}"
        if record['capture']:
            line += f" — {record['capture']}"
        await bot.send_message(chat_id=chat_id, text=line)

        if not record['capture']:
            return
        path = os.path.join(DIG_CAPTURE_DIR, os.path.basename(record['capture']))
        if not os.path.exists(path):
            await bot.send_message(chat_id=chat_id, text=f"⚠️ Capture file {record['capture']} is missing.")
            return
        # Re-encode through OpenCV: JPEGs written by cv2.imwrite are
        # rejected by Telegram (Image_process_failed); imencode output works.
        img = cv2.imread(path)
        if img is None:
            await bot.send_message(chat_id=chat_id, text=f"⚠️ Capture {record['capture']} is unreadable.")
            return
        ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            await bot.send_message(chat_id=chat_id, text=f"⚠️ Capture {record['capture']} failed to re-encode.")
            return
        try:
            await bot.send_photo(
                chat_id=chat_id,
                photo=BytesIO(buf.tobytes()),
                caption=f"📸 {record['time']} — {record['capture']}",
            )
        except Exception as e:
            await bot.send_message(
                chat_id=chat_id, text=f"⚠️ Couldn't send capture {record['capture']}: {e}")


def _log_send_result(future):
    if future.cancelled():
        return
    exc = future.exception()
    if exc:
        print(f'[-] Telegram send failed: {exc}')
