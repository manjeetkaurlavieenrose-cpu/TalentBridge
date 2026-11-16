#!/bin/bash
# Starts a demonstration copy with fictional candidates and scored assessments, kept in demo-data/ (separate from data/).
cd "$(dirname "$0")"
[ -d .venv ] || ./setup_mac.command
source .venv/bin/activate
DATA_DIR="$PWD/demo-data" DEMO_SEED=1 python3 run.py --load-demo-candidates --open "$@"
echo
read -n 1 -s -r -p "TalentBridge stopped. Press any key to close this window."
