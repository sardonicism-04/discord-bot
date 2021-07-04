# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2021 sardonicism-04
import asyncio
import logging
from typing import Optional

from .formatters import format_exception


class PeriodicTimer:
    """Implements simple async periodicity with a coroutine callback"""

    __slots__ = (
        "callback",
        "interval",
        "instance",
        "is_stopped",
        "logger",
        "task"
    )

    def __init__(self, callback, interval: int):
        self.callback = callback
        self.interval = interval
        self.instance = None
        self.is_stopped = False
        self.logger = logging.getLogger(callback.__module__)

    def __get__(self, instance: Optional[object], owner):
        if instance is None:
            return self

        self.instance = instance
        return self

    def start(self):
        self.task = asyncio.create_task(self.runner())

    def shutdown(self):
        if not self.task.done():
            self.is_stopped = True

    def cancel(self):
        if not self.task.done():
            self.task.cancel()

    async def runner(self):
        while True:
            await asyncio.sleep(self.interval)
            try:
                if self.instance:
                    await self.callback(self.instance)
                else:
                    await self.callback()
            except BaseException as e:
                self.logger.error(format_exception(e))
            if self.is_stopped:
                self.cancel()


def periodic(interval: int = 60):
    def inner(func):
        return PeriodicTimer(func, interval)
    return inner
