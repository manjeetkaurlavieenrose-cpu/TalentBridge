#!/bin/bash
# Double-click this file in Finder to start TalentBridge (after the one-time setup in MAC_SETUP_GUIDE.md). It opens the browser.
cd "$(dirname "$0")"
[ -d .venv ] || ./setup_mac.command
source .venv/bin/activate
python3 run.py --open "$@"
echo
read -n 1 -s -r -p "TalentBridge stopped. Press any key to close this window."
