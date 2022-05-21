# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from typing import Any
from discord.ext import commands

from .checks import is_registered_guild, is_registered_profile
from .patcher import Patcher


def shorten(text: str, width: int) -> str:
    if len(text) > width:
        text = text[:width - 3] + "..."
    return text


def try_or_none(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception:
        return None


async def convert_setting(ctx, mapping, setting, new_value):
    # Use try/except here because, if the __getitem__ succeeds,
    # it's roughly 30% faster than using dict.get. Because of the
    # subsequent operations on success, optimizing speed on success
    # is preferable. __getitem__ is slower than dict.get on failure,
    # but since failure leads straight to a `raise`, the difference is
    # negligible.
    try:
        valid_setting = mapping[setting]
    except KeyError:
        raise commands.BadArgument(
            "That's not a valid setting! "
            "Try `settings` for a list of settings!"
        )

    converter = valid_setting["converter"]
    if isinstance(converter, commands.Converter):
        if (converted := await converter.convert(ctx, new_value)) is not None:
            value = converted

    elif (converted := try_or_none(converter, new_value)) is not None:
        value = converted

    else:
        raise commands.BadArgument(
            "Bad value provided for setting `{}`".format(setting)
        )

    return value


def recursive_getattr(target: Any, attr: str, default: Any = None) -> Any:
    # Get the named attribute from the target object
    # with a default of None
    found = getattr(target, attr, None)
    # If nothing is found, return the default
    if not found:
        return default

    # If `found` has no attribute named `attr` then return it
    # Otherwise, recurse until we do find something
    return found if not hasattr(found, attr) else \
        recursive_getattr(found, attr, default)
