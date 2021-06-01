import neo
from discord.ext import commands
from neo.modules.eval import Eval, env_from_context, format_exception
from neo.modules.paginator import Pages, Paginator
from neo.types.converters import CodeblockConverter


class Devel(neo.Addon):
    """Developer-only utility commands"""

    def __init__(self, bot):
        self.bot = bot
        self._eval_scope = {}
        self._last_eval_result = None

    async def cog_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    @commands.guild_only()
    @commands.command(name="cleanup", aliases=["clean"])
    async def dev_cleanup(self, ctx, amount: int = 5):
        """Cleanup the bot's messages from a channel"""

        can_manage = ctx.channel.permissions_for(ctx.me).manage_messages
        if can_manage:
            def check(message):
                return any([
                    message.author == ctx.me,
                    message.content.startswith(ctx.prefix)
                ])
        else:
            def check(message):
                return message.author == ctx.me

        purged = await ctx.channel.purge(
            limit=amount,
            bulk=can_manage,
            check=check
        )
        await ctx.send(f"Cleaned {len(purged)} message(s).", delete_after=5)

    @commands.command(name="eval", aliases=["e"])
    async def dev_eval(self, ctx, *, code: CodeblockConverter):
        """Executes some code, retaining the result"""

        (environment := env_from_context(ctx)).update(**self._eval_scope | globals())

        pages = Pages(
            "\r",
            1500,
            prefix="```py\n",
            suffix="\n```",
            use_embed=True
        )
        menu = Paginator(pages)

        try:
            async for res in Eval(code, environment, self._eval_scope):
                if res is None:
                    continue

                self._last_eval_result = res
                res = repr(res) if not isinstance(res, str) else res
                menu.pages.append("\n{}".format(res))

                if not menu.running:
                    await menu.start(ctx, as_reply=True)

            await ctx.message.add_reaction("\U00002611")

        except Exception as e:
            menu.pages.append("\n{}".format(format_exception(e)))
            await menu.start(ctx, as_reply=True)


def setup(bot):
    bot.add_cog(Devel(bot))
