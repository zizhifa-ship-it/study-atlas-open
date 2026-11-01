#!/bin/sh
set -eu
CDPATH= cd -- "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python server.py --open "$@"
fi
if command -v python3 >/dev/null 2>&1; then
  exec python3 server.py --open "$@"
fi
printf '%s\n' 'Python 3.9 or newer is required. Install it from https://www.python.org/downloads/' >&2
exit 1
