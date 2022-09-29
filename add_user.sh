#!/bin/bash

LUID=$(echo $ID | sed -e 's/^.*uid=\([0-9]*\).*$/\1/')
LGID=$(echo $ID | sed -e 's/^.*gid=\([0-9]*\).*$/\1/')

USER_ID=${LUID:-9001}
GROUP_ID=${LGID:-9001}

echo "Starting with UID : $USER_ID, GID: $GROUP_ID"
useradd -u $USER_ID -o -m user
groupmod -g $GROUP_ID user
export HOME=/home/user

