#!/bin/sh

SESSION_NAME=minecraft
SERVER_PATH=/mnt/disks/minecraft/server/
XMX=1G
XMS=2G
SERVER_JAR=server.jar

cd $SERVER_PATH || exit
echo "start minecraft server"
screen -dmS $SESSION_NAME sudo java -Xms$XMS -Xmx$XMX -jar $SERVER_JAR nogui