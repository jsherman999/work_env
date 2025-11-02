#!/bin/bash
# Start mock environment for development
cd "$(dirname "$0")/.."
echo "Starting mock environment..."
docker compose down  # Clean slate
docker compose up --build
