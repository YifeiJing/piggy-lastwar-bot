# -*- coding: utf-8 -*-
"""Cooperative task cancellation.

The engine sets kill_event when /kill is requested; BaseTask helpers
(check_exists / wait_and_click) raise TaskKilled from the running task, so
even a task stuck in a dead loop unwinds at its next screen check."""
import threading


class TaskKilled(Exception):
    """Raised inside a task when the user requests a kill."""


kill_event = threading.Event()
