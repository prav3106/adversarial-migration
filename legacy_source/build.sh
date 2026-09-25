#!/usr/bin/env bash
# build.sh — compile every COBOL module under legacy_source/
# Usage: ./legacy_source/build.sh
# Requires: GnuCOBOL (cobc) — programs compiled as stand-alone executables with cobc -x
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${SCRIPT_DIR}/bin"
mkdir -p "${BIN_DIR}"

# Load COBC_BIN from .env if present, default to 'cobc'
if [ -f "${SCRIPT_DIR}/../.env" ]; then
  # shellcheck disable=SC1091
  set -a; source "${SCRIPT_DIR}/../.env"; set +a
fi
COBC="${COBC_BIN:-cobc}"

compile_program() {
  local src="$1"
  local name
  name="$(basename "${src}" .cbl)"
  echo "Compiling ${name}..."
  "${COBC}" -x -free -I "${SCRIPT_DIR}" \
    -o "${BIN_DIR}/${name}" \
    "${src}"
  echo "  -> ${BIN_DIR}/${name}"
}

for cbl in "${SCRIPT_DIR}"/*.cbl; do
  compile_program "${cbl}"
done

echo ""
echo "Build complete. Executables in ${BIN_DIR}/"
