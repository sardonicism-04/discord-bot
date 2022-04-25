# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
import asyncio
import logging
import sys
import time

import discord
from aiohttp import ClientSession
from asyncpg import create_pool
from discord.ext import commands

from .modules import *  # noqa: F403
from .tools import *  # noqa: F403
from .types import (
    Embed,
    containers,
    context,
    formatters,
    help_command,
    partials
)

__version__ = "0.14.0a"

log = logging.getLogger(__name__)
intents = discord.Intents(
    **dict.fromkeys(["messages", "guilds", "guild_reactions", "message_content"], True))


class Neo(commands.Bot):
    def __init__(self, config, **kwargs):
        self.cfg = config
        self.boot_time = int(time.time())
        self.session = None
        self.profiles: dict[int, containers.NeoUser] = {}
        self.configs: dict[int, containers.NeoGuildConfig] = {}

        kwargs["command_prefix"] = self.get_prefix
        kwargs["activity"] = discord.Activity(
            name=config["bot"]["activity_name"],
            type=discord.ActivityType[config["bot"]["activity_type"]],
            url="https://twitch.tv/#"  # for spoofing Discord when activity type is streaming
        )
        kwargs["status"] = discord.Status[config["bot"]["status"]]
        kwargs["allowed_mentions"] = discord.AllowedMentions.none()
        kwargs["help_command"] = help_command.NeoHelpCommand()
        kwargs["intents"] = intents
        kwargs["case_insensitive"] = True

        super().__init__(**kwargs)

        self.cooldown = commands.CooldownMapping.from_cooldown(
            2, 4, commands.BucketType.user)
        self.add_check(self.global_cooldown, call_once=True)  # Register global cooldown
        self.add_check(self.channel_check, call_once=True)  # Register channel disabled check
        self.add_check(self.guild_disabled_check)  # Register command disabled check

        self._async_ready = asyncio.Event()

    async def __ainit__(self) -> None:
        self.session = ClientSession()
        self.db = await create_pool(**self.cfg["database"])

        # Load initial profiles from database
        for record in await self.db.fetch("SELECT * FROM profiles"):
            await self.add_profile(record["user_id"], record=record)

        # Load initial guild configurations from database
        for record in await self.db.fetch("SELECT * FROM guild_configs"):
            await self.add_config(record["guild_id"], record=record)

        self._async_ready.set()
        await self.verify_configs()

    async def wait_until_ready(self):
        await self._async_ready.wait()
        return await super().wait_until_ready()

    async def verify_configs(self) -> None:
        """Purges configs where the bot is no longer in the corresponding guild"""
        await self.wait_until_ready()

        for guild_id in self.configs.copy():
            if not self.get_guild(guild_id):
                await self.delete_config(guild_id)

    async def add_profile(self, user_id, *, record=None):
        if not record:
            record = await self.db.fetchrow(
                """
                INSERT INTO profiles (
                    user_id
                ) VALUES (
                    $1
                ) RETURNING *
                """,
                user_id
            )
        profile = containers.NeoUser(pool=self.db, **record)
        self.profiles[user_id] = profile
        return profile

    async def delete_profile(self, user_id: int):
        self.profiles.pop(user_id, None)
        await self.db.execute(
            """
            DELETE FROM
                profiles
            WHERE
                user_id=$1
            """,
            user_id
        )
        self.broadcast("profile_delete", user_id)

    async def add_config(self, guild_id: int, *, record=None):
        if not record:
            record = await self.db.fetchrow(
                """
                INSERT INTO guild_configs (
                    guild_id
                ) VALUES (
                    $1
                ) RETURNING *
                """,
                guild_id
            )
        config = containers.NeoGuildConfig(pool=self.db, **record)
        self.configs[guild_id] = config
        return config

    async def delete_config(self, guild_id: int):
        self.configs.pop(guild_id, None)
        await self.db.execute(
            """
            DELETE FROM
                guild_configs
            WHERE
                guild_id=$1
            """,
            guild_id
        )
        self.broadcast("config_delete", guild_id)

    async def start(self):
        for addon in self.cfg["addons"]:
            await self.load_extension(addon)

        async with self:
            await super().start(self.cfg["bot"]["token"])

    async def close(self):
        await self.session.close()
        await self.db.close()
        await super().close()

    async def on_ready(self):
        log.info(f"{self.user} has received ready event")

    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.content != before.content:
            await self.process_commands(after)

    async def get_prefix(self, message: discord.Message) -> list[str]:
        if message.guild:
            return commands.when_mentioned_or(getattr(
                self.configs.get(message.guild.id),
                "prefix",
                self.cfg["bot"]["prefix"]
            ))(self, message)

        return commands.when_mentioned_or(self.cfg["bot"]["prefix"])(self, message)

    async def on_error(self, *args, **kwargs):
        log.error("\n" + formatters.format_exception(sys.exc_info()))

    async def on_command_error(self, ctx, error):
        original_error = getattr(error, "original", error)
        if original_error.__class__.__name__ in self.cfg["bot"]["ignored_exceptions"]:
            return  # Ignore exceptions specified in config

        try:
            await ctx.send(original_error)
        except discord.Forbidden:
            pass  # Maybe we can't send messages in the channel
        log.error(f"In command invocation: {ctx.message.content}\n" + formatters
                  .format_exception(original_error))

    async def get_context(self, message: discord.Message, *, cls=context.NeoContext):
        return await super().get_context(message, cls=cls)

    def get_user(self, id, *, as_partial=False):
        user = self._connection.get_user(id)
        if as_partial or not user:
            user = partials.PartialUser(state=self._connection, id=id)
        return user

    async def on_guild_remove(self, guild: discord.Guild):
        await self.delete_config(guild.id)

    async def global_cooldown(self, ctx: context.NeoContext):
        if await self.is_owner(ctx.author):
            return True

        retry_after = self.cooldown.update_rate_limit(ctx.message)
        if retry_after:
            raise commands.CommandOnCooldown(
                self.cooldown, retry_after, commands.BucketType.user)
        return True

    async def channel_check(self, ctx: context.NeoContext):
        if any([
            getattr(ctx.guild, "id", None) not in self.configs,
            await self.is_owner(ctx.author),
            ctx.channel.permissions_for(ctx.author).administrator
        ]):
            return True

        if ctx.channel.id in self.configs[ctx.guild.id].disabled_channels:
            raise commands.DisabledCommand("Commands are disabled in this channel.")
        return True

    async def guild_disabled_check(self, ctx: context.NeoContext):
        if any([
            getattr(ctx.guild, "id", None) not in self.configs,
            await self.is_owner(ctx.author),
            ctx.channel.permissions_for(ctx.author).administrator
        ]):
            return True

        if str(ctx.command) in self.configs[ctx.guild.id].disabled_commands:
            raise commands.DisabledCommand("This command is disabled in this server.")
        return True

    # discord.py's `Client.dispatch` API is both private and *volatile*.
    # This serves as a similar implementation that will not change in the future.

    def broadcast(self, event: str, *args, **kwargs):
        coros = []
        for addon in self.cogs.values():
            if event in addon.__receivers__:
                coros.append(addon.__receivers__[event](addon, *args, **kwargs))

        async def run_coros():
            await asyncio.gather(*coros)
        asyncio.create_task(run_coros())
