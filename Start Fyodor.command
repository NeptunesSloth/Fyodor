#!/bin/bash
# Double-click to host game night on macOS (Linux: run scripts/start.sh). Installs on the first run,
# downloads the cards, starts Fyodor and opens the table.
cd "$(dirname "$0")" && exec scripts/start.sh "$@"
