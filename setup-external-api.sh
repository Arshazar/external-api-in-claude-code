#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.9 or newer is required. Install Python, then rerun this script." >&2
  exit 1
fi
exec python3 "$script_dir/setup_external_api.py" "$@"
