#!/bin/bash
# Stop mock environment
cd "$(dirname "$0")/.."
echo "Stopping mock environment..."
docker compose down
