# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2021 sardonicism-04
import asyncio
import contextlib
import zoneinfo
from abc import ABCMeta, abstractmethod
from functools import cache
from typing import Optional


def add_hook(attr_name: str):
    """
    Registers this method as a hook for the given attribute.

    This hook will be called whenever the attribute is accessed.

    Parameters
    ----------
    attr_name: str
        The attribute which is to be hooked

    Returns
    -------
    Any
        The decorated method must return a type. Usually, this is
        a transformed version of the original attribute
    """
    def inner(func):
        setattr(func, "_hooks_to", attr_name)
        return func
    return inner


class RecordContainer(metaclass=ABCMeta):
    """
    Provides an OOP interface for getting data from and updating a database record
    """
    __slots__ = ("ready", "pool", "hooks")

    def __init__(self, *, pool, **record):
        super().__setattr__("ready", False)
        super().__setattr__("pool", pool)

        for key, value in record.items():
            setattr(self, key, value)

        super().__setattr__("ready", True)

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        super().__setattr__(instance, "hooks", {})

        for name in dir(instance):
            attr = getattr(instance, name, None)
            if hasattr(attr, "_hooks_to"):
                instance.hooks[attr._hooks_to] = attr

        super().__setattr__(instance, "ready", True)
        return instance

    def __repr__(self):
        return "<{0.__class__.__name__}>".format(self)

    def __setattr__(self, attribute, value):
        if attribute not in self.__slots__:
            raise AttributeError("{0.__class__.__name__!r} object has no attribute {1!r}".format(
                self, attribute))
        if getattr(self, "ready", False):
            asyncio.create_task(self.update_relation(attribute, value))

        super().__setattr__(attribute, value)

    def __getattribute__(self, attribute):
        value = object.__getattribute__(self, attribute)
        if (hook := object.__getattribute__(self, "hooks").get(attribute)):
            value = hook(value)
        return value

    @abstractmethod
    async def update_relation(self, attribute, value):
        ...

    @abstractmethod
    async def reset_attribute(self, attribute):
        """
        Resets the value of an attribute to its database default.
        """
        ...


class NeoUser(RecordContainer):
    __slots__ = (
        "user_id",
        "hl_blocks",
        "receive_highlights",
        "created_at",
        "timezone",
        "hl_timeout"
    )

    def __repr__(self):
        return "<{0.__class__.__name__} user_id={0.user_id}>".format(self)

    @add_hook("timezone")
    @cache
    def cast_timezone(self, timezone: Optional[str] = None) -> Optional[zoneinfo.ZoneInfo]:
        if timezone is not None:
            return zoneinfo.ZoneInfo(timezone)
        return None

    async def update_relation(self, attribute, value):
        await self.pool.execute(
            f"""
            UPDATE profiles
            SET
                {attribute}=$1
            WHERE
                user_id=$2
            """,    # While it isn't ideal to use string formatting with SQL,
            value,  # the class implements __slots__, so possible attribute names are restricted
            self.user_id
        )

    async def reset_attribute(self, attribute):
        if attribute not in self.__slots__:
            raise AttributeError("{0.__class__.__name__!r} object has no attribute {1!r}".format(
                self, attribute))

        value = await self.pool.fetchval(
            f"""
            UPDATE profiles
            SET
                {attribute}=DEFAULT
            WHERE
                user_id=$1
            RETURNING
                {attribute}
            """,
            self.user_id
        )
        super().__setattr__(attribute, value)


class NeoGuildConfig(RecordContainer):
    __slots__ = ("guild_id", "prefix", "starboard")

    def __repr__(self):
        return "<{0.__class__.__name__} guild_id={0.guild_id}>".format(self)

    async def update_relation(self, attribute, value):
        await self.pool.execute(
            f"""
            UPDATE guild_configs
            SET
                {attribute}=$1
            WHERE
                guild_id=$2
            """,    # While it isn't ideal to use string formatting with SQL,
            value,  # the class implements __slots__, so possible attribute names are restricted
            self.guild_id
        )

    async def reset_attribute(self, attribute):
        if attribute not in self.__slots__:
            raise AttributeError("{0.__class__.__name__!r} object has no attribute {1!r}".format(
                self, attribute))

        value = await self.pool.fetchval(
            f"""
            UPDATE guild_configs
            SET
                {attribute}=DEFAULT
            WHERE
                guild_id=$1
            RETURNING
                {attribute}
            """,
            self.guild_id
        )
        super().__setattr__(attribute, value)


class TimedSet(set):
    def __init__(
        self,
        *args,
        decay_time: int = 60,
        loop: asyncio.AbstractEventLoop = None,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.decay_time = decay_time
        self.loop = loop or asyncio.get_event_loop()
        self.running = {}

        for item in self:
            self.add(item)

    def add(self, item):
        with contextlib.suppress(KeyError):
            con = self.running.pop(item)
            con.cancel()

        super().add(item)
        task = self.loop.create_task(self.decay(item))
        self.running[item] = task

    async def decay(self, item):
        await asyncio.sleep(self.decay_time)
        self.discard(item)
        self.running.pop(item, None)
