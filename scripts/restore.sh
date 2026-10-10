#!/usr/bin/env bash
# Restore output_data + config_data volumes from an archive made by backup.sh.
# EXISTING VOLUME CONTENTS ARE REPLACED.
#
# Usage:
#   docker compose stop          # API/UI must not be running
#   ./scripts/restore.sh backups/reliability-modeler-<project>-<stamp>.tar.gz [-y]
#   docker compose up -d
#
# Environment:
#   COMPOSE_PROJECT_NAME  target compose project (default: repo directory name)

set -euo pipefail

usage() { echo "usage: $0 <archive.tar.gz> [-y]" >&2; exit 2; }
[ $# -ge 1 ] || usage

ARCHIVE_ARG="$1"
ASSUME_YES="${2:-}"
[ -f "${ARCHIVE_ARG}" ] || { echo "ERROR: archive not found: ${ARCHIVE_ARG}" >&2; exit 1; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "${REPO_ROOT}" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')}"
HELPER_IMAGE="${HELPER_IMAGE:-busybox:1.37}"
APP_UID=10001   # appuser in the API image

ARCHIVE_DIR="$(cd "$(dirname "${ARCHIVE_ARG}")" && pwd)"
ARCHIVE_NAME="$(basename "${ARCHIVE_ARG}")"
OUTPUT_VOL="${PROJECT}_output_data"
CONFIG_VOL="${PROJECT}_config_data"

# Refuse to restore underneath a running container.
for v in "${OUTPUT_VOL}" "${CONFIG_VOL}"; do
  running="$(docker ps -q --filter "volume=${v}")"
  if [ -n "${running}" ]; then
    echo "ERROR: volume ${v} is in use by a running container. Run 'docker compose stop' first." >&2
    exit 1
  fi
done

# Validate archive layout before touching anything.
if ! docker run --rm -v "${ARCHIVE_DIR}:/backup:ro" "${HELPER_IMAGE}" \
     sh -c "tar tzf '/backup/${ARCHIVE_NAME}' | grep -Eq '^(\./)?(output|config)/'"; then
  echo "ERROR: ${ARCHIVE_NAME} does not look like a backup.sh archive (expects output/ and config/)." >&2
  exit 1
fi

echo "About to REPLACE the contents of ${OUTPUT_VOL} and ${CONFIG_VOL} with ${ARCHIVE_NAME}."
if [ "${ASSUME_YES}" != "-y" ]; then
  read -r -p "Continue? [y/N] " answer
  case "${answer}" in [yY]|[yY][eE][sS]) ;; *) echo "Aborted."; exit 1;; esac
fi

docker volume create "${OUTPUT_VOL}" >/dev/null
docker volume create "${CONFIG_VOL}" >/dev/null

docker run --rm \
  -v "${OUTPUT_VOL}:/data/output" \
  -v "${CONFIG_VOL}:/data/config" \
  -v "${ARCHIVE_DIR}:/backup:ro" \
  "${HELPER_IMAGE}" \
  sh -euc "
    find /data/output -mindepth 1 -delete
    find /data/config -mindepth 1 -delete
    tar xzf '/backup/${ARCHIVE_NAME}' -C /data
    chown -R ${APP_UID}:${APP_UID} /data/output /data/config
  "

echo "Restore complete. Start the stack with: docker compose up -d"
