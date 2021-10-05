# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2021 sardonicism-04
from datetime import datetime

import neo
from discord.ext import commands
from neo.modules import ButtonsMenu
from neo.tools import convert_setting, is_registered_profile
from neo.types.converters import (
    mention_converter,
    timeout_converter,
    timezone_converter
)

SETTINGS_MAPPING = {
    "receive_highlights": {
        "converter": commands.converter._convert_to_bool,
        "description": None
    },
    "timezone": {
        "converter": timezone_converter(),
        "description": None
    },
    "hl_timeout": {
        "converter": timeout_converter(),
        "description": None
    }
}


class Profile(neo.Addon):
    """
    neo phoenix's profile management module

    Create a profile to gain access to features such as:
    - Todos
    - Highlights
    ...and more!
    """

    def __init__(self, bot: neo.Neo):
        self.bot = bot
        bot.loop.create_task(self.__ainit__())

    async def __ainit__(self):
        await self.bot.wait_until_ready()

        for col_name in SETTINGS_MAPPING.keys():
            col_desc = await self.bot.db.fetchval(
                """
                SELECT get_column_description(
                    $1, 'profiles', $2
                )
                """,
                self.bot.cfg["database"]["database"],
                col_name
            )

            SETTINGS_MAPPING[col_name]["description"] = col_desc

    @commands.group(name="profilesettings", aliases=["settings"])
    @is_registered_profile()
    async def profile_settings(self, ctx):
        """Group command for managing profile settings"""

    @profile_settings.command(name="list")
    @is_registered_profile()
    async def profile_settings_list(self, ctx):
        """
        Displays an overview of your profile settings

        Descriptions of the settings are also provided here
        """
        profile = self.bot.profiles[ctx.author.id]
        embeds = []

        for setting, setting_info in SETTINGS_MAPPING.items():
            description = setting_info["description"].format(
                getattr(profile, setting)
            )
            embed = neo.Embed(
                title=f"Settings for {ctx.author}",
                description=f"**Setting: `{setting}`**\n\n" + description
            ).set_thumbnail(
                url=ctx.author.display_avatar
            )
            embeds.append(embed)

        menu = ButtonsMenu.from_embeds(embeds)
        await menu.start(ctx)

    @profile_settings.command(name="set")
    @is_registered_profile()
    async def profile_settings_set(self, ctx, setting, *, new_value):
        """
        Updates the value of a profile setting

        More information on the available settings and their functions is in the `settings` command
        """
        value = await convert_setting(ctx, SETTINGS_MAPPING, setting, new_value)
        profile = self.bot.profiles[ctx.author.id]
        setattr(profile, setting, value)
        self.bot.broadcast("user_settings_update", ctx.author, profile)
        await ctx.send(f"Setting `{setting}` has been changed!")

    @profile_settings.command(name="reset")
    @is_registered_profile()
    async def profile_settings_reset(self, ctx, setting):
        """
        Resets the value of a profile setting to its default

        Defaults can be found in the `settings` command
        """
        if not SETTINGS_MAPPING.get(setting):
            raise commands.BadArgument(
                "That's not a valid setting! "
                "Try `settings` for a list of settings!"
            )
        profile = self.bot.profiles[ctx.author.id]
        await profile.reset_attribute(setting)
        self.bot.broadcast("user_settings_update", ctx.author, profile)
        await ctx.send(f"Setting `{setting}` has been reset!")

    @commands.group(invoke_without_command=True)
    async def profile(self, ctx, *, user: int | mention_converter = None):
        """Displays the neo profile of yourself, or a specified user."""
        if user is None:
            await is_registered_profile().predicate(ctx)

        profile = self.bot.profiles.get(user or ctx.author.id)
        if profile is None:
            raise AttributeError("This user doesn't have a neo profile!")

        embed = neo.Embed(
            description=(
                f"**<@{user or ctx.author.id}>'s neo profile**\n\n"
                f"**Created** <t:{int(profile.created_at.timestamp())}>"
            )
        ).set_thumbnail(
            url=ctx.me.display_avatar if user else ctx.author.display_avatar
        )
        if getattr(profile, "timezone", None):
            embed.add_field(
                name="Time",
                value="**Timezone** {0}\n**Local Time** {1:%B %d, %Y %H:%M}".format(
                    profile.timezone,
                    datetime.now(profile.timezone)
                ),
                inline=False
            )
        await ctx.send(embed=embed)

    @profile.command(name="create")
    async def profile_create(self, ctx):
        """Creates your neo profile!"""
        if ctx.author.id in self.bot.profiles:
            raise RuntimeError("You already have a profile!")

        profile = await self.bot.add_profile(ctx.author.id)
        self.bot.broadcast("user_settings_update", ctx.author, profile)
        await ctx.send("Successfully initialized your profile!")

    @profile.command(name="delete")
    @is_registered_profile()
    async def profile_delete(self, ctx):
        """__Permanently__ deletes your neo profile"""
        if await ctx.prompt_user(
            "Are you sure you want to delete your profile?"
            "\nThis will delete your profile and all associated "
            "info (todos, highlights, etc), and **cannot** be undone.",
            label_confirm="I'm sure. Delete my profile.",
            label_cancel="Nevermind, don't delete my profile.",
            content_confirmed="Confirmed. Your profile is being deleted."
        ) is False:
            return

        await self.bot.delete_profile(ctx.author.id)


def setup(bot):
    bot.add_cog(Profile(bot))
