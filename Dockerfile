FROM python:3.10
USER root

RUN apt-get update
RUN apt-get install screen -y
ENV WORK_DIR /workspace/discord-bot

RUN mkdir -p $WORK_DIR
WORKDIR $WORK_DIR

COPY pyproject.toml poetry.lock ./
RUN pip install --upgrade pip
RUN pip install poetry
RUN poetry install --no-root

ENTRYPOINT screen poetry run python main.py
