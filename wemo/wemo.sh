#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo $DIR
source "$DIR/.venv/bin/activate"
python3 "$DIR/wemo.py" "$@"
deactivate