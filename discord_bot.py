import logging

import discord
from discord.ext import commands


class DiscordBot(commands.Bot):
    def __init__(self, extensions: list[str]):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="/", intents=intents)
        self._extensions = extensions
        self._logger = logging.getLogger(__name__)

    async def setup_hook(self) -> None:
        for cog in self._extensions:
            await self.load_extension(cog)
            self._logger.debug(f"load extension: {cog}")

    async def on_ready(self):
        for guild in self.guilds:
            guild_obj = discord.Object(guild.id)
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
        guilds = ",".join(
            [f"(name={guild.name},id={guild.id})" for guild in self.guilds]
        )
        self._logger.debug(f"DiscordBot.on_ready: bot={self.user}, guilds=[{guilds}]")
