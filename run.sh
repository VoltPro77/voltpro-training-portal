#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate
export FLASK_APP=server.py
flask db upgrade
flask seed
python server.py
