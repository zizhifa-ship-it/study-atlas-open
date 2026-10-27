#!/bin/zsh
cd -- "${0:A:h}"
if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python server.py --open
fi
exec /usr/bin/python3 server.py --open
