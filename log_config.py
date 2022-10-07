import json
from logging import config


def load(path: str = "log_config.json"):
    with open(path, "r", encoding="utf-8") as file:
        log_config = json.load(file)

    config.dictConfig(log_config)
