#!/bin/bash
# Compatibility entry point; no automatic installation. EPL-2.0.
set -euo pipefail
exec python3 "$(cd -- "$(dirname -- "$0")" && pwd)/sudo_yubikey.py" "$@"
