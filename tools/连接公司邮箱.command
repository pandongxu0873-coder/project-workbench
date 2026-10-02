#!/bin/zsh
cd -- "$(dirname "$0")/.." || exit 1
tools/.communication-venv/bin/python tools/mail_source.py
result=$?
printf "\n按回车关闭。"
read -r reply
exit $result
