# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2022 sardonicism-04
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord
import neo
from discord.ext import commands

if TYPE_CHECKING:
    from neo import Neo


class PromptButton(discord.ui.Button):
    view: PromptActions

    def __init__(self, edited_content: str, value: bool, **kwargs):
        self.edited_content = edited_content
        self.value = value
        super().__init__(**kwargs)

    async def callback(self, interaction: discord.Interaction):
        embed = neo.Embed(description=self.edited_content)
        [setattr(button, "disabled", True) for button in self.view.children]
        await interaction.response.edit_message(embed=embed, view=self.view)
        self.view.stop()
        self.view.value = self.value


class PromptActions(discord.ui.View):
    value: Optional[bool]

    def __init__(
        self,
        ctx,
        *,
        content_confirmed: str,
        content_cancelled: str,
        label_confirm: str,
        label_cancel: str
    ):
        super().__init__()
        self.ctx = ctx
        for content, value, style, label in [
            (content_confirmed, True, discord.ButtonStyle.green, label_confirm),
            (content_cancelled, False, discord.ButtonStyle.red, label_cancel)
        ]:
            self.add_item(PromptButton(content, value, style=style, label=label))
        self.value = None

    async def interaction_check(self, interaction):
        (predicates := []).append(interaction.user.id in (
            self.ctx.author.id,
            *self.ctx.bot.owner_ids,
            self.ctx.bot.owner_id)
        )
        return all(predicates)


class NeoContext(commands.Context['Neo']):
    async def prompt_user(
        self,
        prompt_message: str,
        *,
        content_confirmed: str = "Confirmed",
        content_cancelled: str = "Cancelled",
        label_confirm: str = "✓",
        label_cancel: str = "⨉"
    ):
        actions = PromptActions(
            self,
            content_confirmed=content_confirmed,
            content_cancelled=content_cancelled,
            label_confirm=label_confirm,
            label_cancel=label_cancel
        )
        embed = neo.Embed(description=prompt_message)
        await self.send(embed=embed, view=actions)
        await actions.wait()
        return actions.value

    async def send(self, *args, **kwargs) -> discord.Message:
        if self.interaction is not None:
            await self.interaction.response.send_message(*args, ephemeral=getattr(self, "ephemeral", True), **kwargs)
            return await self.interaction.original_message()
        else:
            return await super().send(*args, **kwargs)
