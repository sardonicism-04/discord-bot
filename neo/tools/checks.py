from discord.ext import commands


def is_registered_profile():
    """Verify the registration status of a user profile"""
    def predicate(ctx):
        if not ctx.bot.get_profile(ctx.author.id):
            raise commands.CommandInvokeError(AttributeError(
                "Looks like you don't have an existing profile! "
                "You can fix this with the `profile create` command."
            ))
        return True
    return commands.check(predicate)


def is_registered_guild():
    """Verify the registration status of a guild"""
    def predicate(ctx):
        if not ctx.bot.get_server(ctx.guild.id):
            raise commands.CommandInvokeError(AttributeError(
                "Looks like this server doesn't have an existing config entry. "
                "You can fix this with the `server create` command."
            ))
        return True
    return commands.check(predicate)
