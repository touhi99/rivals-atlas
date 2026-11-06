#!/bin/bash
# Rivals Atlas: install what is missing on the first run, then open the dashboard.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
WHEEL="$(ls "$HERE"/rivals_atlas-*.whl 2>/dev/null | head -n 1)"

# The launcher ships the OpenSSL 3 libraries LadybugDB needs, so Homebrew is not required.
if [ -d "$HERE/openssl/$(uname -m)" ]; then
  export RIVALS_ATLAS_OPENSSL_DIR="$HERE/openssl/$(uname -m)"
fi

if ! command -v uv >/dev/null 2>&1; then
  if [ -x "$HOME/.local/bin/uv" ]; then
    export PATH="$HOME/.local/bin:$PATH"
  else
    echo "Installing Rivals Atlas for the first time. This takes a minute or two..."
    curl -LsSf https://astral.sh/uv/install.sh | sh || {
      echo "Could not install uv. Check the internet connection and try again."
      read -r -p "Press return to close."
      exit 1
    }
    export PATH="$HOME/.local/bin:$PATH"
  fi
fi

APPDIR="$HOME/Library/Application Support/Rivals Atlas"
mkdir -p "$APPDIR"
cd "$APPDIR" || exit 1

# Prefer the published package (it keeps itself current); fall back to the wheel in this folder.
FROM="rivals-atlas"
if ! uvx --from rivals-atlas rivals-atlas --help >/dev/null 2>&1; then
  if [ -z "$WHEEL" ]; then
    echo "Rivals Atlas is not published yet and this folder has no wheel."
    echo "Download the release zip again and keep the files together."
    read -r -p "Press return to close."
    exit 1
  fi
  FROM="$WHEEL"
fi

echo "Starting Rivals Atlas. Close this window to stop it."
uvx --from "$FROM" rivals-atlas serve --open || {
  echo
  echo "Rivals Atlas could not start. The message above says why."
  read -r -p "Press return to close."
  exit 1
}
