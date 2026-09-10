# Last War: Survival WSL Automation Toolkit

Modular, lightweight automation toolkit tailored for Windows Android Emulators connected via ADB to WSL2.

## Structure
- `core/`: Low-overhead ADB streaming screencap and human-like input tap/swipe driver.
- `vision/`: Normalized cross-correlation template matching.
- `tasks/`: Composable daily task workflows (Alliance Tech, Resource harvesting).
- `tools/`: Screenshot capture tool for quick asset sampling.
- `assets/`: Sub-images for template matching.
- `config.py`: Host ADB bridge IP and resolution configurations.

## Quickstart
1. `pip install -r requirements.txt`
2. Run `python3 tools/capture_tool.py` to get standard frames and slice buttons into `assets/`.
3. Run `python3 main.py`.

## Telegram Remote Control
1. Create a bot with [@BotFather](https://t.me/BotFather) and copy its token.
2. Set `TELEGRAM_BOT_TOKEN` in `config.py`.
3. Run `python3 main.py` and send any message to your bot — it replies with your chat id.
4. Add that id to `TELEGRAM_ALLOWED_CHATS` in `config.py` and restart.

Commands: `/status`, `/screenshot`, `/capture [prefix]`, `/ocr [text]`,
`/run <help|dig|lucky_gift|launch|flower>`, `/pause`, `/resume`, `/stop`, `/start`,
`/kill`, `/stats`, `/report`, `/history [n]`, `/record <id>`, `/tap <x> <y>`,
`/swipe <x1> <y1> <x2> <y2> [ms]`, `/back`, `/help`.

## Activity Log
Every completed help/dig/lucky-gift task and every actual game launch is stored in
the SQLite database `logs/activity.db` (table `activity`: `id`, `time`, `event`,
`capture`). The reward screen is captured right after the gift is collected and
saved to `dig_captures/` (`dig_*.jpg` / `lucky_gift_*.jpg`); the record references
it by file name.

Example query:
`sqlite3 logs/activity.db "SELECT * FROM activity ORDER BY id DESC LIMIT 10;"`

## Tests
Dry-run tests (fake screen, no device/Telegram): `venv/bin/python -m unittest discover -s tests -v`.
