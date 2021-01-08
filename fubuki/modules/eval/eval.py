import traceback
from inspect import isasyncgenfunction

import import_expression

from .compiler import compile_all


def format_exception(error):
    return "".join(traceback.format_exception(type(error), error, error.__traceback__))


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


def clear_intersection(dict1, dict2):
    for key in dict1.keys():
        dict2.pop(key, None)


class Eval:
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
            yield await coro(*args, **kwargs) or ""
