# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
import asyncio
import inspect
import re
from collections import defaultdict
from functools import cached_property
from operator import attrgetter

import discord
import neo
from discord.ext import commands
from neo.modules import ButtonsMenu
from neo.tools import is_registered_profile
from neo.types.containers import TimedSet
from neo.types.timer import periodic

DEFAULT_AVATARS = [
    "<:_:863449882088833065>",
    "<:_:863449883121418320>",
    "<:_:863449884157280307>",
    "<:_:863449885088808970>",
    "<:_:863449885834739712>",
    "<:_:863449887403147314>"
]
MAX_TRIGGERS = 10
MAX_TRIGGER_LEN = 100
CUSTOM_EMOJI = re.compile(r"<a?:[a-zA-Z0-9_]{2,}:\d+>")


def format_hl_context(message: discord.Message, is_trigger=False):
    fmt = (
        "[{0} **{1.author.display_name}**]({1.jump_url}) {1.content}"
        if is_trigger else
        "{0} **{1.author.display_name}** {1.content}"
    )
    message.content = CUSTOM_EMOJI.sub("❔", message.content)  # Replace custom emojis to preserve formatting
    if message.attachments:
        message.content += " *[Attachment x{}]*".format(len(message.attachments))
    if message.embeds:
        message.content += " *[Embed x{}]*".format(len(message.embeds))
    if message.stickers:
        message.content += " *[Sticker x{}]*".format(len(message.stickers))

    return fmt.format(
        DEFAULT_AVATARS[int(message.author.default_avatar.key)],
        message
    )


class Highlight:
    __slots__ = ("bot", "content", "user_id", "pattern")

    def __init__(self, bot: neo.Neo, *, content, user_id):
        self.bot = bot
        self.content = content
        self.user_id = user_id
        self.pattern = re.compile(fr"\b{self.content}\b", re.I)

    def __repr__(self):
        return ("<{0.__class__.__name__} user_id={0.user_id!r} "
                "content={0.content!r}>").format(self)

    async def predicate(self, message):
        if not message.guild:
            return
        if any([message.author.id == self.user_id,
                message.author.bot]):
            return
        if self.bot.profiles[self.user_id].receive_highlights is False:
            return  # Don't highlight users who have disabled highlight receipt

        blacklist = self.bot.profiles[self.user_id].hl_blocks
        if any(attrgetter(attr)(message) in blacklist for attr in (
                "id", "guild.id", "channel.id", "author.id")
               ):
            return

        if self.user_id in [m.id for m in message.mentions]:
            return  # Don't highlight users with messages they are mentioned in

        try:  # This lets us update the channel members and make sure the user exists
            member = await message.guild.fetch_member(self.user_id, cache=True)
        except discord.NotFound:
            return

        if isinstance(message.channel, discord.Thread):
            if message.channel.is_private():  # Need to fetch members explicitly
                try:
                    await message.channel.fetch_member(self.user_id)
                    members = [member]  # If member is in thread, then they pass
                except discord.NotFound:
                    return  # Otherwise... they don't
            else:
                members = message.channel.parent.members
        else:
            members = message.channel.members
        if member not in members:  # Check channel membership
            return

        return True

    async def to_send_kwargs(self, message, later_triggers: set[discord.Message]):
        content = ""
        triggers: set[discord.Message] = {message, *later_triggers}
        async for m in message.channel.history(limit=6, around=message):
            if len(content + m.content) > 1500:  # Don't exceed embed limits
                m.content = "*[Omitted due to length]*"
            formatted = format_hl_context(m, m in triggers)
            content = f"{formatted}\n{content}"

        embed = neo.Embed(
            title="In {0.guild.name}/#{0.channel.name}".format(message),
            description=content
        )

        view = discord.ui.View(timeout=0)
        view.add_item(discord.ui.Button(url=message.jump_url, label="Jump to message"))

        return {
            "content": "{0.author}: {0.content}".format(message)[:1500],
            "embed": embed,
            "view": view
        }

    def matches(self, other):
        return self.pattern.search(other)


class Highlights(neo.Addon):
    """Commands for managing highlights"""

    def __init__(self, bot: neo.Neo):
        self.bot = bot
        self.highlights: defaultdict[int, list[Highlight]] = defaultdict(list)
        self.grace_periods: dict[int, TimedSet] = {}
        self.queued_highlights: defaultdict[int, dict] = defaultdict(dict)
        asyncio.create_task(self.__ainit__())

    async def __ainit__(self):
        await self.bot.wait_until_ready()

        for record in await self.bot.db.fetch("SELECT * FROM highlights"):
            self.highlights[record["user_id"]].append(Highlight(self.bot, **record))

        for profile in self.bot.profiles.values():
            self.grace_periods[profile.user_id] = TimedSet(
                timeout=profile.hl_timeout * 60
            )

        self.send_queued_highlights.start()

    def cog_unload(self):
        self.send_queued_highlights.shutdown()

    @cached_property  # Cache to avoid being re-computed after every message
    def flat_highlights(self):
        return [hl for hl_list in self.highlights.values() for hl in hl_list]

    def recompute_flattened(self):
        if hasattr(self, "flat_highlights"):
            del self.flat_highlights
        self.flat_highlights

    @commands.Cog.listener("on_message")
    async def listen_for_highlights(self, message):
        if not self.bot.is_ready():
            return  # Return if bot is not ready, so flat_highlights is computed correctly

        if message.author.id in {hl.user_id for hl in self.flat_highlights}:
            self.grace_periods[message.author.id].add(message.channel.id)

        for hl in filter(lambda hl: hl.matches(message.content), self.flat_highlights):
            if message.channel.id in self.grace_periods[hl.user_id]:
                continue
            if not await hl.predicate(message):
                continue
            channel_queue = self.queued_highlights[message.channel.id]
            if hl.user_id not in self.queued_highlights[message.channel.id]:
                channel_queue[hl.user_id] = (hl, message, set())
            else:
                channel_queue[hl.user_id][2].add(message)

    @periodic(5)
    async def send_queued_highlights(self):
        queue = self.queued_highlights.copy()
        self.queued_highlights.clear()
        for hl, message, later_triggers in [
            pair for nested in queue.values() for pair in nested.values()
        ]:
            await self.bot.get_user(hl.user_id, as_partial=True).send(
                **await hl.to_send_kwargs(message, later_triggers)
            )

    @neo.Addon.recv("user_settings_update")
    async def handle_update_profile(self, user, profile):
        if self.grace_periods.get(user.id):
            current_timeout = self.grace_periods[user.id].timeout
            if (profile.hl_timeout * 60) == current_timeout:
                return
            self.grace_periods.pop(user.id).clear()

        self.grace_periods[profile.user_id] = TimedSet(
            timeout=profile.hl_timeout * 60
        )

    # Need to dynamically account for deleted profiles
    @neo.Addon.recv("profile_delete")
    async def handle_deleted_profile(self, user_id: int):
        if (popped := self.grace_periods.pop(user_id, None)) is not None:
            popped.clear()  # Cleanup TimedSet
        self.highlights.pop(user_id, None)
        self.recompute_flattened()

    async def cog_check(self, ctx):
        return await is_registered_profile().predicate(ctx)

    @commands.hybrid_group(aliases=["hl"])
    async def highlight(self, ctx):
        """Group command for managing highlights"""

    @highlight.command(name="list")
    async def highlight_list(self, ctx: neo.context.NeoContext):
        """List your highlights"""
        description = ""
        user_highlights = self.highlights.get(ctx.author.id, [])

        for index, hl in enumerate(user_highlights, 1):
            description += "`{0}` `{1}`\n".format(
                index,
                hl.content
            )

        embed = neo.Embed(description=description or "You have no highlights") \
            .set_footer(text=f"{len(user_highlights)}/{MAX_TRIGGERS} slots used") \
            .set_author(name=f"{ctx.author}'s highlights", icon_url=ctx.author.avatar)

        if not ctx.interaction:
            return await ctx.send(embed=embed)
        await ctx.interaction.response.send_message(embeds=[embed], ephemeral=True)

    @highlight.command(name="add")
    async def highlight_add(self, ctx, *, content):
        """
        Add a new highlight

        Highlights will notify you when the word/phrase you add is mentioned

        **Notes**
        - Highlights will __never__ be triggered from private threads
        - Highlights will __never__ be triggered by bots
        - You must be a member of a channel to be highlighted in it
        """
        if len(content) <= 1:
            raise ValueError("Highlights must contain more than 1 character.")
        elif len(content) >= MAX_TRIGGER_LEN:
            raise ValueError(
                f"Highlights cannot be longer than {MAX_TRIGGER_LEN:,} characters!")

        if len(self.highlights.get(ctx.author.id, [])) >= MAX_TRIGGERS:
            raise ValueError("You've used up all of your highlight slots!")

        if content in [hl.content for hl in self.highlights.get(ctx.author.id, [])]:
            raise ValueError("Cannot have multiple highlights with the same content.")

        result = await self.bot.db.fetchrow(
            """
            INSERT INTO highlights (
                user_id,
                content
            ) VALUES ( $1, $2 )
            RETURNING *
            """,
            ctx.author.id,
            content
        )
        self.highlights[ctx.author.id].append(Highlight(self.bot, **result))
        self.recompute_flattened()

        if not ctx.interaction:
            await ctx.message.add_reaction("\U00002611")
        else:
            await ctx.interaction.response.send_message("\U00002611", ephemeral=True)

    @highlight.command(name="remove", aliases=["rm"])
    @discord.app_commands.describe(
        index="A highlight index to remove, or \"~\" to clear all highlights"
    )
    async def highlight_remove(self, ctx, index: str):
        """
        Remove a highlight by index

        Passing `~` will remove all highlights at once
        """
        indices = [*filter(lambda ind: ind == "~" or isinstance(ind, int),
                           int(index) if index != "~" else index)]

        if "~" in indices:
            highlights = self.highlights.get(ctx.author.id, []).copy()
            self.highlights.pop(ctx.author.id, None)

        else:
            (indices := [*map(str, indices)]).sort(reverse=True)  # Pop in an way that preserves the list's original order
            try:
                highlights = [self.highlights[ctx.author.id].pop(index - 1) for index in map(
                    int, filter(str.isdigit, indices))
                ]
            except IndexError:
                raise IndexError("One or more of the provided indices is invalid.")

        await self.bot.db.execute(
            """
            DELETE FROM
                highlights
            WHERE
                user_id = $1 AND
                content = ANY($2::TEXT[])
            """,
            ctx.author.id,
            [*map(attrgetter("content"), highlights)]
        )
        self.recompute_flattened()

        if not ctx.interaction:
            await ctx.message.add_reaction("\U00002611")
        else:
            await ctx.interaction.response.send_message("\U00002611", ephemeral=True)

    @highlight_remove.autocomplete("index")
    async def highlight_remove_autocomplete(self, interaction: discord.Interaction, current: str):
        if interaction.user.id not in self.bot.profiles:
            return []

        (opts := ["~"]).extend([*range(1, len(self.highlights[interaction.user.id]) + 1)][:24])
        return [*map(
            lambda opt: discord.app_commands.Choice(name=opt, value=opt),
            map(str, opts)
        )]

    def perform_blocklist_action(self, *, profile, ids, action="block"):
        blacklist = {*profile.hl_blocks, }
        ids = {*ids, }

        if action == "unblock":
            blacklist -= ids
        else:
            blacklist |= ids

        profile.hl_blocks = [*blacklist]

    @highlight.command(name="block", usage="<id>")
    @discord.app_commands.describe(
        id="The ID of a user, server, or channel to block",
        user="A user to block",
        channel="A channel to block"
    )
    async def highlight_block(
        self,
        ctx,
        id: str = None,
        user: discord.User | discord.Member = None,
        channel: discord.TextChannel = None
    ):
        """Block a target from highlighting you"""
        if not id.isnumeric():
            raise commands.BadArgument("Please input a valid ID.")

        profile = self.bot.profiles[ctx.author.id]

        if ctx.interaction:
            ids = [*map(lambda obj: int(getattr(obj, "id", obj)), filter(None, [user, channel, id]))]
        else:
            if not id:
                raise commands.MissingRequiredArgument(commands.Parameter(
                    name="id", kind=inspect.Parameter.POSITIONAL_ONLY))
            ids = [id]

        self.perform_blocklist_action(profile=profile, ids=ids)

        if not ctx.interaction:
            await ctx.message.add_reaction("\U00002611")
        else:
            await ctx.interaction.response.send_message("\U00002611", ephemeral=True)

    @highlight.command(name="blocklist")
    async def highlight_block_list(self, ctx):
        """
        Manage a blocklist for highlights.
        """
        profile = self.bot.profiles[ctx.author.id]

        def transform_mention(id):
            mention = getattr(self.bot.get_guild(id), "name",
                              getattr(self.bot.get_channel(id), "mention",
                                      f"<@{id}>"))  # Yes, this could lead to fake user mentions
            return "`{0}` [{1}]".format(id, mention)

        menu = ButtonsMenu.from_iterable(
            [*map(transform_mention, profile.hl_blocks)] or ["No highlight blocks"],
            per_page=10,
            use_embed=True,
            template_embed=neo.Embed().set_author(
                name=f"{ctx.author}'s highlight blocks",
                icon_url=ctx.author.display_avatar
            )
        )
        await menu.start(ctx)

    @highlight.command(name="unblock")
    async def highlight_unblock(self, ctx, id: str):
        """
        Unblock entities from triggering your highlights

        Servers, users, and channels can all be unblocked via ID

        One *or more* IDs can be provided to this command
        """
        if not id.isnumeric():
            raise commands.BadArgument("Please input a valid ID.")

        profile = self.bot.profiles[ctx.author.id]

        self.perform_blocklist_action(profile=profile, ids=[int(id)], action="unblock")

        if not ctx.interaction:
            await ctx.message.add_reaction("\U00002611")
        else:
            await ctx.interaction.response.send_message("\U00002611", ephemeral=True)

    @highlight_unblock.autocomplete("id")
    async def highlight_unblock_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ):
        profile = self.bot.profiles[interaction.user.id]

        def transform_mention(id):
            mention = getattr(self.bot.get_guild(id), "name",
                              getattr(self.bot.get_channel(id), "name",
                                      getattr(self.bot.get_user(id), "name", "Unknown")))
            return "{0} [{1}]".format(id, mention)

        return [
            discord.app_commands.Choice(name=transform_mention(_id), value=str(_id))
            for _id in profile.hl_blocks
        ][:25]


async def setup(bot):
    await bot.add_cog(Highlights(bot))
