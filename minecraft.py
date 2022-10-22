import asyncio
import datetime
import enum
import json
import logging
import os
from typing import Optional

import discord
import google.cloud.compute_v1.services.instances
from discord import app_commands
from discord.ext import commands, tasks
from google.oauth2 import service_account

logger = logging.getLogger(__name__)


class Operation(enum.Enum):
    start = 1
    stop = 2
    status = 3


class MinecraftCog(commands.Cog):
    GOOGLE_CREDENTIALS_FILE = os.environ["GOOGLE_CREDENTIALS_FILE"]
    SERVER_PROJECT_ID = os.environ["GOOGLE_MINECRAFT_SERVER_PROJECT_ID"]
    SERVER_ZONE = os.environ["GOOGLE_MINECRAFT_SERVER_ZONE"]
    SERVER_INSTANCE_NAME = os.environ["GOOGLE_MINECRAFT_SERVER_INSTANCE_NAME"]
    MONITERING_SERVER_STATUS_TIME = float(
        os.getenv("MONITERING_SERVER_STATUS_TIME", 60 * 5)
    )
    SERVER_AUTO_STOP_TIME = float(os.getenv("SERVER_AUTO_STOP_TIME", 60 * 60 * 24))
    SERVER_START_LOG_FILE = "server_start_log.json"

    STATUS_RUNNING = "RUNNING"
    STATUS_TERMINATED = "TERMINATED"

    def __init__(self, bot: commands.Bot):
        self._bot = bot

        credentials = service_account.Credentials.from_service_account_file(
            self.GOOGLE_CREDENTIALS_FILE
        )
        self._instances_client = (
            google.cloud.compute_v1.services.instances.InstancesClient(
                credentials=credentials
            )
        )

    def cog_load(self):
        logger.debug("called")
        self.observe_server_status.start()

    def cog_unload(self) -> None:
        logger.debug("called")
        self.observe_server_status.cancel()

    @tasks.loop(seconds=MONITERING_SERVER_STATUS_TIME)
    async def observe_server_status(self):
        logger.debug("called")
        instance = self.get_instance()
        await self.update_bot_status(instance.status)
        await self.stop_server_if_needed(instance.status)

    @app_commands.command(name="minecraft", description="Minecraftサーバーに命令を投げるコマンド")
    @app_commands.describe(operation="サーバーへの命令の種別を選択してください")
    async def minecraft(self, interaction: discord.Interaction, operation: Operation):
        logger.debug(f"called: operation={operation}")
        if operation == Operation.start:
            await self.start_server(interaction)
        elif operation == Operation.stop:
            await self.stop_server(interaction)
        elif operation == Operation.status:
            await self.status_server(interaction)

    async def start_server(self, interaction: discord.Interaction):
        instance = self.get_instance()
        logger.debug(f"status={instance.status}")

        if instance.status == self.STATUS_RUNNING:
            await interaction.response.send_message(
                f"{self.SERVER_INSTANCE_NAME} はすでに起動しています"
            )
            return

        if instance.status != self.STATUS_TERMINATED:
            await interaction.response.send_message(
                f"{self.SERVER_INSTANCE_NAME} の状態は {instance.status} です"
            )
            return

        logger.debug("starting instance")
        self.start_instance()
        await interaction.response.defer()

        await self.wait_server_status(self.STATUS_RUNNING)

        logger.debug("started instance")
        await interaction.followup.send(content=f"{self.SERVER_INSTANCE_NAME} が起動しました")

        self.write_server_start_log(interaction.channel.id)
        await self.update_bot_status(self.STATUS_RUNNING)

    async def stop_server(self, interaction: discord.Interaction):
        instance = self.get_instance()
        logger.debug(f"status={instance.status}")

        if instance.status == self.STATUS_TERMINATED:
            await interaction.response.send_message(
                f"{self.SERVER_INSTANCE_NAME} はすでに停止しています"
            )
            return

        if instance.status != self.STATUS_RUNNING:
            await interaction.response.send_message(
                f"{self.SERVER_INSTANCE_NAME} の状態は {instance.status} です"
            )
            return

        logger.debug("stopping instance")
        self.stop_instance()
        await interaction.response.defer()

        await self.wait_server_status(self.STATUS_TERMINATED)

        logger.debug("stopped instance")
        await interaction.followup.send(content=f"{self.SERVER_INSTANCE_NAME} が停止しました")

        self.delete_server_start_log()
        await self.update_bot_status(self.STATUS_TERMINATED)

    async def status_server(self, interaction: discord.Interaction):
        instance = self.get_instance()
        logger.debug(f"status={instance.status}")

        if instance.status == self.STATUS_RUNNING:
            message = f"{self.SERVER_INSTANCE_NAME} は起動中です"
        elif instance.status == self.STATUS_TERMINATED:
            message = f"{self.SERVER_INSTANCE_NAME} は停止中です"
        else:
            message = f"{self.SERVER_INSTANCE_NAME} の状態は {instance.status} です"

        await interaction.response.send_message(message)
        await self.update_bot_status(instance.status)

    async def update_bot_status(self, status: str):
        if status == self.STATUS_RUNNING:
            activity = discord.Game(name=f"Minecraftサーバー({self.SERVER_INSTANCE_NAME})")
        else:
            activity = None

        # 初回だけNoneを指定したときにTypeErrorが出るので応急処置
        try:
            await self._bot.change_presence(activity=activity)
        except Exception as e:
            logger.error(e)

        logger.debug(f"update activity: {status}")

    async def stop_server_if_needed(self, status: str):
        start_log = self.read_server_start_log()
        if start_log is None:
            return
        diff = datetime.datetime.now() - start_log["start_at"]
        if diff.total_seconds() < self.SERVER_AUTO_STOP_TIME:
            return
        if status != self.STATUS_RUNNING:
            return

        logger.debug("stopping instance")
        self.stop_instance()

        await self.wait_server_status(self.STATUS_TERMINATED)

        channel = self._bot.get_channel(start_log["channel_id"])
        if channel is not None:
            await channel.send(
                content=f"起動してから{self.SERVER_AUTO_STOP_TIME}秒経過したため、"
                        f" {self.SERVER_INSTANCE_NAME} を自動停止しました"
            )
        logger.debug("stopped instance")

        self.delete_server_start_log()
        await self.update_bot_status(self.STATUS_TERMINATED)

    async def wait_server_status(self, status: str, delay=1):
        while True:
            instance = self.get_instance()
            if instance.status == status:
                break
            await asyncio.sleep(delay)

    def start_instance(self):
        return self._instances_client.start(
            project=self.SERVER_PROJECT_ID,
            zone=self.SERVER_ZONE,
            instance=self.SERVER_INSTANCE_NAME,
        )

    def stop_instance(self):
        return self._instances_client.stop(
            project=self.SERVER_PROJECT_ID,
            zone=self.SERVER_ZONE,
            instance=self.SERVER_INSTANCE_NAME,
        )

    def get_instance(self):
        return self._instances_client.get(
            project=self.SERVER_PROJECT_ID,
            zone=self.SERVER_ZONE,
            instance=self.SERVER_INSTANCE_NAME,
        )

    def write_server_start_log(self, channel_id: int):
        output = dict(
            instance=self.SERVER_INSTANCE_NAME,
            start_at=datetime.datetime.now(),
            channel_id=channel_id,
        )
        with open(self.SERVER_START_LOG_FILE, "w", encoding="utf-8") as file:
            json.dump(output, file, default=_serialize_json)

    def read_server_start_log(self) -> Optional[dict]:
        if not os.path.exists(self.SERVER_START_LOG_FILE):
            return None
        with open(self.SERVER_START_LOG_FILE, "r", encoding="utf-8") as file:
            return json.load(file, object_hook=_deserialize_json)

    def delete_server_start_log(self):
        if not os.path.exists(self.SERVER_START_LOG_FILE):
            return
        os.remove(self.SERVER_START_LOG_FILE)


def _serialize_json(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    return str(obj)


def _deserialize_json(obj):
    for (key, value) in obj.items():
        try:
            obj[key] = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f")
        except:
            pass
    return obj


async def setup(bot: commands.Bot):
    await bot.add_cog(MinecraftCog(bot))
