#!/usr/bin/env bash
# Back up the Reliability Modeler data volumes (output_data + config_data)
# into a single timestamped tar.gz.
#
# Usage:
#   ./scripts/backup.sh [BACKUP_DIR]          (default: ./backups)
#
# Environment:
#   COMPOSE_PROJECT_NAME  compose project whose volumes to back up
#                         (default: name of the repository directory)
#
# Safe to run while the stack is up: the API writes files atomically
# (tmp file + rename). For a guaranteed-quiescent copy, stop the api service
# first: docker compose stop api

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "${REPO_ROOT}" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')}"
BACKUP_DIR="${1:-${REPO_ROOT}/backups}"
HELPER_IMAGE="${HELPER_IMAGE:-busybox:1.37}"

OUTPUT_VOL="${PROJECT}_output_data"
CONFIG_VOL="${PROJECT}_config_data"

for v in "${OUTPUT_VOL}" "${CONFIG_VOL}"; do
  if ! docker volume inspect "${v}" >/dev/null 2>&1; then
    echo "ERROR: volume ${v} not found (set COMPOSE_PROJECT_NAME?)" >&2
    exit 1
  fi
done

mkdir -p "${BACKUP_DIR}"
BACKUP_DIR="$(cd "${BACKUP_DIR}" && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="reliability-modeler-${PROJECT}-${STAMP}.tar.gz"

echo "Backing up ${OUTPUT_VOL} + ${CONFIG_VOL} -> ${BACKUP_DIR}/${ARCHIVE}"
# umask 077: the archive is created 0600 inside the helper (on Linux it would
# otherwise be a root-owned 0644 file). It is then handed to the invoking user
# and only renamed into place once tar has succeeded.
docker run --rm \
  -v "${OUTPUT_VOL}:/data/output:ro" \
  -v "${CONFIG_VOL}:/data/config:ro" \
  -v "${BACKUP_DIR}:/backup" \
  "${HELPER_IMAGE}" \
  sh -euc "
    umask 077
    tar czf '/backup/${ARCHIVE}.partial' -C /data output config
    chown $(id -u):$(id -g) '/backup/${ARCHIVE}.partial'
    mv '/backup/${ARCHIVE}.partial' '/backup/${ARCHIVE}'
  "

echo "Done: ${BACKUP_DIR}/${ARCHIVE} ($(du -h "${BACKUP_DIR}/${ARCHIVE}" | cut -f1))"
