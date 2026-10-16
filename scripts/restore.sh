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

# Validate the whole archive before touching anything: gzip CRC, a complete
# tar listing (a truncated archive fails here), and both top-level directories.
if ! docker run --rm -v "${ARCHIVE_DIR}:/backup:ro" "${HELPER_IMAGE}" \
     sh -euc "
       gzip -t '/backup/${ARCHIVE_NAME}'
       tar tzf '/backup/${ARCHIVE_NAME}' > /tmp/listing
       grep -Eq '^(\./)?output/' /tmp/listing
       grep -Eq '^(\./)?config/' /tmp/listing
     "; then
  echo "ERROR: ${ARCHIVE_NAME} is corrupt/truncated or not a backup.sh archive (expects output/ and config/). Nothing was changed." >&2
  exit 1
fi

echo "About to REPLACE the contents of ${OUTPUT_VOL} and ${CONFIG_VOL} with ${ARCHIVE_NAME}."
if [ "${ASSUME_YES}" != "-y" ]; then
  read -r -p "Continue? [y/N] " answer
  case "${answer}" in [yY]|[yY][eE][sS]) ;; *) echo "Aborted."; exit 1;; esac
fi

docker volume create "${OUTPUT_VOL}" >/dev/null
docker volume create "${CONFIG_VOL}" >/dev/null

# Extract to a staging dir inside the helper first; the volumes are only
# emptied and refilled once the whole archive has been extracted.
docker run --rm \
  -v "${OUTPUT_VOL}:/data/output" \
  -v "${CONFIG_VOL}:/data/config" \
  -v "${ARCHIVE_DIR}:/backup:ro" \
  "${HELPER_IMAGE}" \
  sh -euc "
    mkdir /stage
    tar xzf '/backup/${ARCHIVE_NAME}' -C /stage
    test -d /stage/output
    test -d /stage/config
    find /data/output -mindepth 1 -delete
    find /data/config -mindepth 1 -delete
    cp -a /stage/output/. /data/output/
    cp -a /stage/config/. /data/config/
    chown -R ${APP_UID}:${APP_UID} /data/output /data/config
  "

echo "Restore complete. Start the stack with: docker compose up -d"
