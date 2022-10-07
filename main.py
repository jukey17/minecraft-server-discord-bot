import asyncio
import os

import dotenv

import log_config
from discord_bot import DiscordBot


async def main():
    dotenv.load_dotenv()
    log_config.load()
    extensions = os.environ["EXTENSIONS"].split(",")
    bot = DiscordBot(extensions=extensions)
    await bot.start(token=os.environ["DISCORD_BOT_TOKEN"])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt as e:
        print(e)
