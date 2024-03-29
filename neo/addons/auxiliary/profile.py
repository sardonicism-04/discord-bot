# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2023 sardonicism-04
"""
An auxiliary module for the `Profile` addon
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord

import neo

if TYPE_CHECKING:
    from ..profile import Profile


class ChangeSettingButton(discord.ui.Button[neo.ButtonsMenu[neo.EmbedPages]]):
    def __init__(
        self,
        *,
        settings: neo.containers.SettingsMapping,
        addon: Profile,
        **kwargs,
    ):
        self.addon = addon
        self.settings = settings

        super().__init__(**kwargs)

    async def callback(self, interaction):
        if not self.view:
            return

        index = self.view.current_page
        current_setting = [*self.settings.values()][index]

        outer_self = self

        class ChangeSettingModal(
            discord.ui.Modal, title="Edit profile settings"
        ):
            new_value = discord.ui.TextInput(
                label=f"Changing {current_setting.display_name}",
                placeholder="New value",
                min_length=1,
                max_length=500,
            )

            async def on_submit(self, interaction):
                if not outer_self.view:
                    return

                try:
                    if self.new_value.value:
                        await outer_self.addon.set_option(
                            interaction,
                            current_setting.key,
                            self.new_value.value,
                        )
                except Exception as e:
                    await interaction.response.send_message(e, ephemeral=True)
                else:
                    await interaction.response.send_message(
                        "Your settings have been updated!", ephemeral=True
                    )

                    description = outer_self.settings[current_setting.key][
                        "description"
                    ].format(
                        getattr(
                            outer_self.addon.bot.profiles[interaction.user.id],
                            current_setting.key,
                        )
                    )
                    outer_self.view.pages.items[index].description = (
                        f"**Setting: `{current_setting.display_name}`**\n\n"
                        + description
                    )
                    await outer_self.view.refresh_page()

        modal = ChangeSettingModal()

        await interaction.response.send_modal(modal)


class ResetSettingButton(discord.ui.Button[neo.ButtonsMenu[neo.EmbedPages]]):
    def __init__(
        self,
        *,
        settings: neo.containers.SettingsMapping,
        addon: Profile,
        **kwargs,
    ):
        self.addon = addon
        self.settings = settings

        super().__init__(**kwargs)

    async def callback(self, interaction):
        if not interaction.guild or not self.view:
            return

        index = self.view.current_page
        current_setting = [*self.settings.values()][index]

        await self.addon.reset_option(interaction, current_setting.key)

        await interaction.response.send_message(
            "Your settings have been updated!", ephemeral=True
        )

        description = self.settings[current_setting.key]["description"].format(
            getattr(
                self.addon.bot.profiles[interaction.user.id],
                current_setting.key,
            )
        )
        self.view.pages.items[index].description = (
            f"**Setting: `{current_setting.display_name}`**\n\n" + description
        )
        await self.view.refresh_page()
