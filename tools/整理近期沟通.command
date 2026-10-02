#!/bin/zsh
cd -- "$(dirname "$0")/.." || exit 1
tools/.communication-venv/bin/python tools/communication_pipeline.py run "$@"
result=$?
printf "\n处理结束。回执路径显示在上方。\n"
exit $result
