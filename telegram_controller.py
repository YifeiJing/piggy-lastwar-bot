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
from vision.annotate import annotate_coordinates

try:
    from config import TELEGRAM_CHAT_ACCESS
except ImportError:
    TELEGRAM_CHAT_ACCESS = {}


class TelegramController:
    """Telegram remote control: commands either mutate engine state directly
    (instant) or are queued for the engine thread (/run). Manual taps/swipes
    execute directly under the driver lock.

    Supports multiple engines (one per game account). Each Telegram chat can
    use /setuser to subscribe to a specific account's notifications and route
    commands to that account's engine.

    IAM: chats are assigned access via TELEGRAM_CHAT_ACCESS in config.
    Value 'admin' grants full access; a list of user_id strings restricts the
    chat to those accounts only. TELEGRAM_ALLOWED_CHATS entries are treated as
    admins for backward compatibility."""

    def __init__(self, engines, driver_map=None):
        # Accept legacy single-engine form: TelegramController(engine, driver)
        if not isinstance(engines, dict):
            uid = getattr(engines, 'user_id', None) or 'default'
            self.engines = {uid: engines}
            self.driver_map = {uid: driver_map} if driver_map is not None else {}
        else:
            self.engines = engines
            self.driver_map = driver_map or {}
        self._active_user = {}  # chat_id -> user_id
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self._loop = None

    # ---- IAM helpers ----

    def _is_authorized(self, chat_id: int) -> bool:
        return chat_id in TELEGRAM_CHAT_ACCESS or chat_id in TELEGRAM_ALLOWED_CHATS

    def _get_accessible_users(self, chat_id: int):
        """Return None (admin — all users) or frozenset of permitted user_ids."""
        access = TELEGRAM_CHAT_ACCESS.get(chat_id)
        if access == 'admin':
            return None
        if isinstance(access, (list, set, frozenset)):
            return frozenset(access)
        # Legacy TELEGRAM_ALLOWED_CHATS entries are admins.
        if chat_id in TELEGRAM_ALLOWED_CHATS:
            return None
        return frozenset()

    def _can_access_user(self, chat_id: int, user_id: str) -> bool:
        accessible = self._get_accessible_users(chat_id)
        return accessible is None or user_id in accessible

    def _accessible_engine_uids(self, chat_id: int) -> dict:
        """Return the subset of engines this chat may access: {uid: engine}."""
        accessible = self._get_accessible_users(chat_id)
        if accessible is None:
            return dict(self.engines)
        return {uid: eng for uid, eng in self.engines.items() if uid in accessible}

    def _resolve_uid(self, chat_id: int):
        """Resolve the active user_id for this chat (IAM + /setuser selection)."""
        available = self._accessible_engine_uids(chat_id)
        if not available:
            return None
        if len(available) == 1:
            return next(iter(available))
        uid = self._active_user.get(chat_id)
        return uid if uid in available else None

    # ---- engine / driver routing ----

    def _get_engine(self, chat_id: int):
        uid = self._resolve_uid(chat_id)
        return self.engines.get(uid) if uid else None

    def _get_driver(self, chat_id: int):
        uid = self._resolve_uid(chat_id)
        return self.driver_map.get(uid) if uid else None

    def _all_authorized_chat_ids(self) -> set:
        return set(TELEGRAM_CHAT_ACCESS.keys()) | set(TELEGRAM_ALLOWED_CHATS)

    # ---- Telegram polling loop ----

    def run(self):
        if not self._all_authorized_chat_ids():
            print('[!] No chats configured — send any message to the bot to learn your chat id.')
        self.application.add_handler(MessageHandler(filters.TEXT, self._on_message))
        print('[*] Telegram controller started, polling...')
        try:
            asyncio.run(self._run())
        except KeyboardInterrupt:
            print('[*] Telegram controller stopped.')
        finally:
            for eng in self.engines.values():
                eng.exit_event.set()

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

    # ---- outbound notifications ----

    def send_message(self, text: str, user_id: str = ''):
        """Called from an engine thread to push events to Telegram.

        Messages are prefixed with [user_id] when multiple engines are running.
        Each chat only receives messages for users it has IAM access to and
        has selected (or all its accessible users when no /setuser was run)."""
        if self._loop is None:
            print(f'[TG] (not sent, bot not ready): {text}')
            return
        prefix = f'[{user_id}] ' if len(self.engines) > 1 and user_id else ''
        full_text = prefix + text
        for chat_id in self._route_to_chats(user_id):
            future = asyncio.run_coroutine_threadsafe(
                self.application.bot.send_message(chat_id=chat_id, text=full_text),
                self._loop,
            )
            future.add_done_callback(_log_send_result)

    def _route_to_chats(self, user_id: str) -> list:
        """Chat ids that should receive a notification for user_id.

        IAM: chats with no access to the user are skipped. Per-chat /setuser
        selection: chats watching a different user are skipped."""
        targets = []
        for chat_id in self._all_authorized_chat_ids():
            if user_id and not self._can_access_user(chat_id, user_id):
                continue
            active = self._active_user.get(chat_id)
            if active is not None and user_id and active != user_id:
                continue
            targets.append(chat_id)
        return targets

    def send_capture(self, user_id: str, capture_name: str, name: str = ''):
        """Called from an engine thread to push a reward capture photo.

        IAM-routed like send_message. The file is re-encoded before sending
        (Telegram rejects JPEGs written by cv2.imwrite)."""
        if self._loop is None:
            print(f'[TG] (not sent, bot not ready): {capture_name}')
            return
        prefix = f'[{user_id}] ' if len(self.engines) > 1 and user_id else ''
        if name:
            caption = f'{prefix}📸 {name} reward — {capture_name}'
        else:
            caption = f'{prefix}📸 {capture_name}'
        for chat_id in self._route_to_chats(user_id):
            future = asyncio.run_coroutine_threadsafe(
                self._send_capture_photo(chat_id, capture_name, caption),
                self._loop,
            )
            future.add_done_callback(_log_send_result)

    async def _send_capture_photo(self, chat_id: int, capture_name: str, caption: str):
        bot = self.application.bot
        path = os.path.join(DIG_CAPTURE_DIR, os.path.basename(capture_name))
        if not os.path.exists(path):
            await bot.send_message(chat_id=chat_id, text=f"⚠️ Capture file {capture_name} is missing.")
            return
        img = cv2.imread(path)
        if img is None:
            await bot.send_message(chat_id=chat_id, text=f"⚠️ Capture {capture_name} is unreadable.")
            return
        ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            await bot.send_message(chat_id=chat_id, text=f"⚠️ Capture {capture_name} failed to re-encode.")
            return
        try:
            await bot.send_photo(
                chat_id=chat_id,
                photo=BytesIO(buf.tobytes()),
                caption=caption,
            )
        except Exception as e:
            await bot.send_message(chat_id=chat_id, text=f"⚠️ Couldn't send capture {capture_name}: {e}")

    def help_text(self, chat_id: int = 0) -> str:
        user_cmds = ''
        accessible = self._accessible_engine_uids(chat_id) if chat_id else self.engines
        if len(accessible) > 1 or (chat_id == 0 and len(self.engines) > 1):
            user_cmds = (
                '/users — list accounts and active selection\n'
                '/setuser <user_id> — subscribe this chat to one account\n'
            )
        return (
            '📖 Commands:\n'
            '/status — engine state + screenshot\n'
            '/screenshot — current screen + coordinate grid\n'
            '/capture [prefix] — save current screen to dig_captures/\n'
            '/ocr [text] — recognize screen text / check if text is on screen\n'
            f"/run <task> — run once: {', '.join(TASK_MAP)}\n"
            '/pause — pause the auto loop\n'
            '/resume — resume the auto loop\n'
            '/kill — abort the running task (dead-loop rescue)\n'
            '/tasks — show which cycle tasks are enabled\n'
            '/enable <task> — enable a cycle task\n'
            '/disable <task> — disable a cycle task\n'
            '/stop — stop the auto loop\n'
            '/start — start/resume the auto loop\n'
            '/stats — today\'s counters\n'
            '/report — stats + screenshot\n'
            '/history [n] — last N records (text only)\n'
            '/record <id> — one record + its capture image\n'
            '/tap <x> <y> — tap the screen\n'
            '/swipe <x1> <y1> <x2> <y2> [ms] — swipe\n'
            '/back — Android back button\n'
            '/resetstats — reset counters\n'
            + user_cmds +
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

        if not self._is_authorized(chat.id):
            await msg.reply_text(
                f'⛔ Unauthorized. Your chat id: {chat.id}\n'
                'Add it to TELEGRAM_CHAT_ACCESS in config.py to gain control.')
            return

        text = msg.text
        if not text.startswith('/'):
            await msg.reply_text(self.help_text(chat.id))
            return

        parts = text.split()
        cmd = parts[0].split('@')[0].lower()
        args = parts[1:]
        await self._dispatch(cmd, args, msg, chat.id)

    async def _dispatch(self, cmd: str, args: list, msg, chat_id: int):
        _engine_cmds = {'/start', '/stop', '/pause', '/resume', '/run', '/kill',
                        '/status', '/stats', '/report', '/history', '/record',
                        '/tasks', '/enable', '/disable'}
        _driver_cmds = {'/screenshot', '/capture', '/ocr', '/tap', '/swipe', '/back'}

        engine = self._get_engine(chat_id)
        driver = self._get_driver(chat_id)

        if cmd in _engine_cmds and engine is None:
            accessible = self._accessible_engine_uids(chat_id)
            if not accessible:
                await msg.reply_text('⛔ You have no access to any account.')
            else:
                await msg.reply_text(
                    f'⚠️ Select an account first.\n'
                    f'/setuser <user_id>  available: {", ".join(accessible)}'
                )
            return
        if cmd in _driver_cmds and driver is None:
            accessible = self._accessible_engine_uids(chat_id)
            if not accessible:
                await msg.reply_text('⛔ You have no access to any account.')
            else:
                await msg.reply_text(
                    f'⚠️ Select an account first.\n'
                    f'/setuser <user_id>  available: {", ".join(accessible)}'
                )
            return

        if cmd == '/start':
            engine.start_loop()
        elif cmd == '/help':
            await msg.reply_text(self.help_text(chat_id))
        elif cmd == '/users':
            accessible = self._accessible_engine_uids(chat_id)
            current = self._active_user.get(chat_id)
            label = current if current else '(all accessible)'
            lines = [f'👥 Accounts (watching: {label}):']
            for uid, eng in accessible.items():
                marker = ' ◀' if uid == current else ''
                lines.append(f'  • {uid} — {eng.status}{marker}')
            await msg.reply_text('\n'.join(lines))
        elif cmd == '/setuser':
            if not args:
                accessible = self._accessible_engine_uids(chat_id)
                await msg.reply_text(
                    f'Usage: /setuser <user_id>\nAvailable: {", ".join(accessible)}'
                )
                return
            uid = args[0]
            if uid not in self.engines:
                await msg.reply_text(
                    f"❌ Unknown user '{uid}'. Available: {', '.join(self.engines)}"
                )
                return
            if not self._can_access_user(chat_id, uid):
                await msg.reply_text(f"⛔ You don't have access to '{uid}'.")
                return
            self._active_user[chat_id] = uid
            await msg.reply_text(f'✅ Now watching: {uid}')
        elif cmd == '/status':
            await msg.reply_text(f'📊 Engine: {engine.status}\n{engine.stats.format_stats()}')
            if not await self._send_screenshot(chat_id, driver):
                await msg.reply_text('❌ Screenshot failed (device not reachable?)')
        elif cmd == '/screenshot':
            if not await self._send_screenshot(chat_id, driver, annotated=True):
                await msg.reply_text('❌ Screenshot failed (device not reachable?)')
        elif cmd == '/capture':
            prefix = ''.join(c for c in args[0] if c.isalnum() or c == '_') if args else 'manual'
            if not prefix:
                prefix = 'manual'
            await self._save_capture(chat_id, driver, prefix)
        elif cmd == '/ocr':
            if args:
                await self._check_text(chat_id, engine, driver, ' '.join(args))
            else:
                await self._recognize_text(chat_id, engine, driver)
        elif cmd == '/stats':
            await msg.reply_text(engine.stats.format_stats())
        elif cmd == '/report':
            await msg.reply_text(f'📊 Engine: {engine.status}\n{engine.stats.format_stats()}')
            if not await self._send_screenshot(chat_id, driver):
                await msg.reply_text('❌ Screenshot failed (device not reachable?)')
        elif cmd == '/history':
            try:
                n = int(args[0]) if args else 10
            except ValueError:
                await msg.reply_text('Usage: /history [n] (1-20)')
                return
            await self._send_history(chat_id, engine, max(1, n))
        elif cmd == '/record':
            try:
                record_id = int(args[0])
            except (ValueError, IndexError):
                await msg.reply_text('Usage: /record <id> — id from /history')
                return
            await self._send_record(chat_id, engine, record_id)
        elif cmd == '/run':
            if not args:
                await msg.reply_text(f"Usage: /run <task>. Available: {', '.join(TASK_MAP)}")
                return
            engine.run_task(args[0].lower())
        elif cmd == '/pause':
            engine.pause()
        elif cmd == '/resume':
            engine.resume()
        elif cmd == '/stop':
            engine.stop_loop()
        elif cmd == '/tasks':
            await msg.reply_text(engine.format_tasks())
        elif cmd == '/enable':
            if not args:
                await msg.reply_text('Usage: /enable <task>')
                return
            engine.enable_task(args[0].lower())
        elif cmd == '/disable':
            if not args:
                await msg.reply_text('Usage: /disable <task>')
                return
            engine.disable_task(args[0].lower())
        elif cmd == '/kill':
            engine.kill_task()
        elif cmd == '/tap':
            try:
                x, y = int(args[0]), int(args[1])
            except (ValueError, IndexError):
                await msg.reply_text('Usage: /tap <x> <y>')
                return
            driver.tap(x, y)
            await msg.reply_text(f'✅ Tapped ({x}, {y})')
        elif cmd == '/swipe':
            try:
                x1, y1, x2, y2 = (int(a) for a in args[:4])
                duration = int(args[4]) if len(args) > 4 else 350
            except (ValueError, IndexError):
                await msg.reply_text('Usage: /swipe <x1> <y1> <x2> <y2> [duration_ms]')
                return
            driver.swipe(x1, y1, x2, y2, duration)
            await msg.reply_text(f'✅ Swiped ({x1},{y1}) -> ({x2},{y2})')
        elif cmd == '/back':
            driver.press_back()
            await msg.reply_text('✅ Back pressed')
        elif cmd == '/resetstats':
            engine.reset_stats()
            await msg.reply_text('✅ Stats reset')
        else:
            await msg.reply_text(f'❓ Unknown command.\n{self.help_text(chat_id)}')

    # ---- helpers ----

    async def _send_screenshot(self, chat_id: int, driver, annotated: bool = False) -> bool:
        img = await asyncio.to_thread(driver.screenshot)
        if img is None:
            return False
        caption = None
        if annotated:
            img = await asyncio.to_thread(annotate_coordinates, img)
            caption = '🖊️ Grid step = 100 px — x along the top, y along the left.'
        ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return False
        await self.application.bot.send_photo(
            chat_id=chat_id, photo=BytesIO(buf.tobytes()), caption=caption)
        return True

    async def _save_capture(self, chat_id: int, driver, prefix: str) -> bool:
        """Save the current screen into dig_captures/ without sending it."""
        img = await asyncio.to_thread(driver.screenshot)
        file_name = save_capture(img, prefix=prefix, capture_dir=DIG_CAPTURE_DIR)
        if file_name:
            await self.application.bot.send_message(
                chat_id=chat_id, text=f'💾 Saved {file_name} to dig_captures/.')
            return True
        await self.application.bot.send_message(
            chat_id=chat_id, text='❌ Screenshot failed (device not reachable?)')
        return False

    async def _recognize_text(self, chat_id: int, engine, driver):
        """OCR the current screen and send all recognized text fragments."""
        img = await asyncio.to_thread(driver.screenshot)
        if img is None:
            await self.application.bot.send_message(
                chat_id=chat_id, text='❌ Screenshot failed (device not reachable?)')
            return
        texts = await asyncio.to_thread(engine.ocr_engine.extract_texts, img)
        if not texts:
            await self.application.bot.send_message(chat_id=chat_id, text='🔤 No text recognized.')
            return
        joined = ' | '.join(texts)
        if len(joined) > 3000:
            joined = joined[:3000] + '…'
        await self.application.bot.send_message(chat_id=chat_id, text=f'🔤 Recognized:\n{joined}')

    async def _check_text(self, chat_id: int, engine, driver, target: str):
        """Check whether target text is visible on the current screen."""
        img = await asyncio.to_thread(driver.screenshot)
        if img is None:
            await self.application.bot.send_message(
                chat_id=chat_id, text='❌ Screenshot failed (device not reachable?)')
            return
        found = await asyncio.to_thread(engine.ocr_engine.check_text_exists, img, target)
        if found:
            await self.application.bot.send_message(
                chat_id=chat_id, text=f"✅ Found '{target}' on screen.")
        else:
            await self.application.bot.send_message(
                chat_id=chat_id, text=f"❌ '{target}' not found on screen.")

    async def _send_history(self, chat_id: int, engine, limit: int):
        """Send the last N activity records as text (no images)."""
        records = engine.logger.fetch_all(limit=limit)
        bot = self.application.bot
        if not records:
            await bot.send_message(chat_id=chat_id, text='📋 No records yet.')
            return

        lines = [f'📋 Last {len(records)} records:']
        for r in records:
            line = f"{r['id']}. [{r['time']}] {r['event']}"
            if r.get('info'):
                line += f" — {r['info']}"
            if r['capture']:
                line += f" — {r['capture']}"
            lines.append(line)
        await bot.send_message(chat_id=chat_id, text='\n'.join(lines))

    async def _send_record(self, chat_id: int, engine, record_id: int):
        """Checkout one record; includes its capture image if it has one."""
        bot = self.application.bot
        record = engine.logger.fetch_by_id(record_id)
        if record is None:
            await bot.send_message(chat_id=chat_id, text=f'❌ No record with id {record_id}.')
            return

        line = f"#{record['id']} [{record['time']}] {record['event']}"
        if record.get('info'):
            line += f" — {record['info']}"
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
