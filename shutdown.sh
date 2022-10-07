#!/bin/sh

SESSION_NAME=minecraft

echo "stop minecraft server"
screen -S $SESSION_NAME -X eval 'stuff "stop"\015'