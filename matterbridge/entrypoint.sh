#!/bin/sh
set -e

# Registering the plugin writes to the storage volume, not the image, so it has
# to happen at runtime. `-add` is idempotent: on every boot after the first it
# logs "already registered" and exits 0.
echo "Registering matterbridge-haus…"
matterbridge -add matterbridge-haus || echo "matterbridge -add returned $? — continuing"

exec "$@"
