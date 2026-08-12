#!/usr/bin/env bash
# Rebuild the LSD Dream Emulator channel WAD from source assets.
#
#   ./build/build.sh
#
# Needs: python venv with Pillow + pycryptodome, wine (for Benzin),
# ImageMagick. Set PY to point at another interpreter if needed.
set -euo pipefail

cd "$(dirname "$0")"
# resolved after the cd, so it is relative to build/ regardless of where invoked
PY="${PY:-$PWD/.venv/bin/python}"

if [ ! -x "$PY" ]; then
  echo "Python venv not found at $PY" >&2
  echo "Create one with:  python3 -m venv .venv && .venv/bin/pip install Pillow pycryptodome" >&2
  echo "then re-run with: PY=.venv/bin/python ./build.sh" >&2
  exit 1
fi

mkdir -p out

echo "==> extracting donor (FCE Ultra GX [Tantric])"
"$PY" tools/extract.py

echo "==> icon.bin"
"$PY" tools/build_icon.py

echo "==> icon preview gif"
"$PY" tools/preview_icon.py

echo "==> banner.bin"
"$PY" tools/build_banner.py

echo "==> sound.bin"
"$PY" tools/build_sound.py

echo "==> forwarder"
"$PY" tools/patch_forwarder.py

echo "==> WAD"
"$PY" tools/build_wad.py

echo "==> verify"
# build_wad.py owns the output name; ask it rather than repeating the string
WAD="$("$PY" -c 'import sys; sys.path.insert(0, "tools"); import build_wad; print(build_wad.OUT)')"
"$PY" tools/verify.py "$WAD"

rm -f out/_splash_src_*.png out/_splash_*.png
