#!/bin/sh
# Builds dist/BillHQ, a single executable with everything inside. Needs Docker.
set -e
cd "$(dirname "$0")/.."
docker build -f packaging/Dockerfile -t billhq-build .
container=$(docker create billhq-build)
mkdir -p dist
docker cp "$container:/out/BillHQ" dist/BillHQ
docker rm "$container" > /dev/null
./dist/BillHQ --version
