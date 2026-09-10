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
    event TEXT NOT NULL,
    capture TEXT
)
"""


class ActivityLogger:
    """SQLite-backed activity log: one row per completed help/dig task.

    Thread-safe: writes are guarded by a lock and the connection allows
    cross-thread use (auto cycle and manual /run both record)."""

    def __init__(self, db_path: str = LOG_DB):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(_SCHEMA)
            self._conn.commit()

    def log_help(self):
        self._insert('help', None)

    def log_dig(self, capture: Optional[str] = None):
        self._insert('dig', capture)

    def log_lucky_gift(self, capture: Optional[str] = None):
        self._insert('lucky_gift', capture)

    def log_launch(self):
        self._insert('launch', None)

    def _insert(self, event: str, capture: Optional[str]):
        with self._lock:
            self._conn.execute(
                'INSERT INTO activity (time, event, capture) VALUES (?, ?, ?)',
                (time.strftime('%Y-%m-%d %H:%M:%S'), event, capture),
            )
            self._conn.commit()

    def fetch_all(self, limit: Optional[int] = None):
        """All records, oldest first. Pass limit for the most recent N."""
        query = 'SELECT * FROM activity ORDER BY id DESC'
        params = ()
        if limit:
            query += ' LIMIT ?'
            params = (int(limit),)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in reversed(rows)]

    def fetch_by_id(self, record_id: int):
        """One record by its id, or None if it doesn't exist."""
        with self._lock:
            row = self._conn.execute(
                'SELECT * FROM activity WHERE id = ?', (int(record_id),)
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
