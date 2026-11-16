#!/bin/bash
# One-time setup on macOS: creates .venv and installs TalentBridge's packages. Needs Python 3.10+ (python.org installer).
# Usage: double-click, or in Terminal: ./setup_mac.command [dev] [postgres] [anthropic]
cd "$(dirname "$0")"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' || { echo "Python 3.10 or newer is required (see MAC_SETUP_GUIDE.md)."; exit 1; }
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
for opt in "$@"; do
  case "$opt" in
    dev) python -m pip install -r requirements-dev.txt ;;
    postgres) python -m pip install -r requirements-postgres.txt ;;
    anthropic) python -m pip install -r requirements-anthropic.txt ;;
  esac
done
[ -f .env ] || cp .env.example .env
# Free AI (optional, no account, runs on this Mac). The app works without it, using the built-in rule-based engine.
if ! command -v ollama >/dev/null && [ ! -d /Applications/Ollama.app ]; then
  if command -v brew >/dev/null; then echo "Installing the free AI engine (Ollama)..."; brew install ollama || true
  else echo "Optional: for the free AI features, install Ollama from https://ollama.com/download and start TalentBridge again (it is found automatically; no account or payment)."; fi
fi
command -v tesseract >/dev/null || echo "Optional: to read scanned CVs, install Tesseract OCR: brew install tesseract"
echo; echo "Setup finished. Start with ./start_mac.command (or ./start_demo_mac.command for sample data), then use http://localhost:5050"
