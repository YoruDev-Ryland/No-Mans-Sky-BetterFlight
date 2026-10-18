#!/usr/bin/env bash
# Kept for convenience: the build is native/build.py (Linux and Windows).
#   ./build.sh [simtest|selftest]   ==   python3 build.py [simtest|selftest]
exec python3 "$(dirname "$0")/build.py" "$@"
