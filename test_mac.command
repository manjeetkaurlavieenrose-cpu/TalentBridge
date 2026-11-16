#!/bin/bash
# Runs the automated tests and an end-to-end check of the real app (temporary data folder; your data is not touched).
cd "$(dirname "$0")"
[ -d .venv ] || ./setup_mac.command dev
source .venv/bin/activate
python -c "import reportlab" 2>/dev/null || python -m pip install -r requirements-dev.txt
(cd backend && python -m unittest discover -s tests -t .) && unit=0 || unit=1
python scripts/smoke_test.py && smoke=0 || smoke=1
echo
if [ "$unit$smoke" = "00" ]; then echo "ALL CHECKS PASSED"; else echo "SOME CHECKS FAILED (see above)"; fi
read -n 1 -s -r -p "Press any key to close this window."
