# -*- coding: utf-8 -*-
"""Activity storage: SQLite records of help/dig completions plus dig gift
screen captures. Records live in logs/activity.db; captures are JPEGs in
dig_captures/ referenced by file name from the dig record."""
import os
import sqlite3
import threading
import time
from datetime import datetime
from typing import Optional

import cv2

from config import DIG_CAPTURE_DIR, LOG_DIR

LOG_DB = os.path.join(LOG_DIR, 'activity.db')

_SCHEMA = """
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT '',
    event TEXT NOT NULL,
    capture TEXT,
    info TEXT
)
"""


class ActivityLogger:
    """SQLite-backed activity log: one row per completed help/dig task.

    Thread-safe: writes are guarded by a lock and the connection allows
    cross-thread use (auto cycle and manual /run both record).

    When user_id is set, fetches are scoped to that user only."""

    def __init__(self, db_path: str = LOG_DB, user_id: str = ''):
        self.db_path = db_path
        self.user_id = user_id
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(_SCHEMA)
            self._conn.commit()
            # Add user_id column to databases that predate this field.
            try:
                self._conn.execute(
                    "ALTER TABLE activity ADD COLUMN user_id TEXT NOT NULL DEFAULT ''"
                )
                self._conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists
            # Add info column (free-text task detail, e.g. joined rally).
            try:
                self._conn.execute("ALTER TABLE activity ADD COLUMN info TEXT")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists

    def log_help(self):
        self._insert('help', None)

    def log_dig(self, capture: Optional[str] = None):
        self._insert('dig', capture)

    def log_lucky_gift(self, capture: Optional[str] = None):
        self._insert('lucky_gift', capture)

    def log_launch(self):
        self._insert('launch', None)

    def log_rally(self, info: Optional[str] = None):
        self._insert('rally', None, info)

    def _insert(self, event: str, capture: Optional[str], info: Optional[str] = None):
        with self._lock:
            self._conn.execute(
                'INSERT INTO activity (time, user_id, event, capture, info) VALUES (?, ?, ?, ?, ?)',
                (time.strftime('%Y-%m-%d %H:%M:%S'), self.user_id, event, capture, info),
            )
            self._conn.commit()

    def fetch_all(self, limit: Optional[int] = None):
        """Records scoped to this logger's user_id, oldest first.
        Pass limit for the most recent N. Empty user_id returns all records."""
        params = []
        where = ''
        if self.user_id:
            where = 'WHERE user_id = ? '
            params.append(self.user_id)
        query = f'SELECT * FROM activity {where}ORDER BY id DESC'
        if limit:
            query += ' LIMIT ?'
            params.append(int(limit))
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in reversed(rows)]

    def fetch_by_id(self, record_id: int):
        """One record by id (scoped to this logger's user_id), or None."""
        where = 'id = ?'
        params = [int(record_id)]
        if self.user_id:
            where += ' AND user_id = ?'
            params.append(self.user_id)
        with self._lock:
            row = self._conn.execute(
                f'SELECT * FROM activity WHERE {where}', params
            ).fetchone()
        return dict(row) if row else None

    def close(self):
        with self._lock:
            self._conn.close()


def save_capture(img, prefix: str = 'dig', capture_dir: str = DIG_CAPTURE_DIR) -> Optional[str]:
    """Save a reward screenshot into the capture dir.

    Returns the file name on success (used as the capture id in records),
    or None if the image is invalid or saving failed."""
    if img is None:
        return None
    # Re-encode through imencode: JPEGs written by cv2.imwrite are rejected
    # by Telegram's image processor when sent later via /history.
    ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        return None
    # datetime.strftime supports %f on every platform; time.strftime does not
    # (glibc leaves it literal, producing names like dig_..._%f.jpg).
    file_name = datetime.now().strftime(f'{prefix}_%Y%m%d_%H%M%S_%f.jpg')
    os.makedirs(capture_dir, exist_ok=True)
    with open(os.path.join(capture_dir, file_name), 'wb') as f:
        f.write(buf.tobytes())
    return file_name
