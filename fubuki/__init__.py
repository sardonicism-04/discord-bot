import pathlib
import asyncio

import discord
from discord.ext import commands

from .modules import *
from .types import Embed

class Fubuki(commands.Bot):
    def __init__(self, config, **kwargs):

        self.cfg = config
        self._last_eval_result = None
        kwargs.setdefault('command_prefix', self.get_prefix)

        super().__init__(**kwargs)

    async def get_prefix(self, message):
        return commands.when_mentioned_or(self.cfg['bot']['prefix'])(self, message)

    def run(self):
        WD = pathlib.Path(__file__).parent / "addons"
        CWD = pathlib.Path(__file__).parents[1]

        for addon in WD.iterdir():
            if addon.name.endswith('.py') and not addon.is_dir():
                _to_load = addon.relative_to(CWD).as_posix().replace('/', '.')[:-3]
                self.load_extension(_to_load)

        super().run(self.cfg['bot']['token'])

    async def on_message_edit(self, before, after):
        if after.content != before.content:
            await self.process_commands(after)

    async def close(self):
        [task.cancel() for task in asyncio.all_tasks(self.loop)]