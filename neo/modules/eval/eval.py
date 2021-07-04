# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2021 sardonicism-04
import traceback
from inspect import isasyncgenfunction

import import_expression

from .compiler import compile_all


def env_from_context(ctx):
    return {
        "ctx": ctx,
        "author": ctx.author,
        "guild": ctx.guild,
        "message": ctx.message,
        "channel": ctx.channel,
        "bot": ctx.bot,
        "_": ctx.cog._last_eval_result,
    }


class Eval:
    __slots__ = ("compiled", "environment", "output")

    def __init__(self, code_input, environment={}, output={}):
        self.compiled = compile_all(code_input)
        self.environment = environment
        self.output = output

    def __aiter__(self):
        import_expression.exec(
            compile(self.compiled, "<eval>", "exec"), self.environment
        )
        _aexec = self.environment["__aexec__"]
        return self.walk_results(_aexec, self.output)

    async def walk_results(self, coro, *args, **kwargs):
        if isasyncgenfunction(coro):
            async for result in coro(*args, **kwargs):
                yield result
        else:
            yield await coro(*args, **kwargs)
