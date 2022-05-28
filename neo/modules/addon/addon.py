# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

from collections.abc import Coroutine
from types import MethodType
from typing import Any, Callable, Protocol, TypeGuard, cast

from discord.ext import commands
from typing_extensions import Self

ReceiverRet = Any | Coroutine[None, None, Any]


class Receiver(Protocol):
    __receiver__: bool
    __event_name__: str

    def __call__(self, addon: Addon, *args: Any, **kwargs: Any) -> ReceiverRet:
        ...


def is_receiver(val: Callable[..., ReceiverRet]) -> TypeGuard[Receiver]:
    return callable(val) and hasattr(val, "__receiver__")


class AddonMeta(commands.CogMeta):
    __receivers__: dict[str, Receiver]

    def __new__(cls, *args, **kwargs):
        _cls = cast(Self, super().__new__(cls, *args, **kwargs))

        receivers = {}

        for attr in vars(_cls).values():
            if not is_receiver(attr):
                continue

            recv_func = attr
            receivers[recv_func.__event_name__] = recv_func

        _cls.__receivers__ = receivers
        return _cls


class Addon(commands.Cog, metaclass=AddonMeta):
    __receivers__: dict[str, Receiver]

    def __init__(self, bot):
        """
        This just removes the mandatory __init__ for every single addon
        """
        self.bot = bot

    def add_command(self, command):
        """
        Add a commands.Command or a subclass of it to a loaded Addon

        If a commands.Group is encountered, all subcommands will also be recursively added
        """
        _original_command = command

        _current_commands = list(self.__cog_commands__)
        _current_commands.append(command)
        self.__cog_commands__ = list(_current_commands)

        for _command in self.__cog_commands__:
            self.bot.remove_command(_command.name)
            _command.cog = self
            if not _command.parent:
                self.bot.add_command(_command)

        if isinstance(_original_command, commands.Group):
            for subcmd in command.walk_commands():
                if isinstance(subcmd, commands.Group):  # Recursively add sub-groups
                    self.add_command(subcmd)
                subcmd.cog = self  # Update the subcmds

        return self.bot.get_command(command.name)

    def add_listener(self, listener, name=None):
        """
        Registers a listener to a loaded Addon
        """
        setattr(
            self,
            listener.__name__,
            MethodType(
                listener.__func__ if isinstance(listener, MethodType) else listener,
                self,
            ),
        )  # Bind the listener to the object as a method
        self.__cog_listeners__.append(
            (name or listener.__name__, listener.__name__)
        )  # Add it to the list

        for name, method_name in self.__cog_listeners__:
            self.bot.remove_listener(getattr(self, method_name))  # Just in case I guess
            self.bot.add_listener(
                getattr(self, method_name), name
            )  # Register it as a listener

    def _merge_addon(self, other):
        """
        Handles merging 2 addons together.
        Generally for internal use
        """
        self.bot.remove_cog(other.qualified_name)  # Consume the other addon
        for _cmd in other.__cog_commands__:  # Add all commands over
            self.add_command(_cmd)
        for name, method_name in other.__cog_listeners__:  # Add all listeners over
            self.add_listener(getattr(other, method_name), name)

    def __or__(self, other):
        """
        Uses the `|` operator to merge two addons together.
        When merged, all commands and listeners from the second addon
        will be added to the first addon, consuming the second addon
        in the process.
        """
        self._merge_addon(other)
        return self

    @staticmethod
    def recv(event: str):
        def inner(func: Callable[..., ReceiverRet]) -> Receiver:
            receiver = func
            receiver.__receiver__ = True
            receiver.__event_name__ = event
            assert is_receiver(receiver), f"Receiver {func!r} failed assertion"
            return receiver

        return inner
