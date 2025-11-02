#!/bin/bash
# Complete fresh start - removes all containers, volumes, and data
cd "$(dirname "$0")/.."
echo "Performing fresh start..."
docker compose down -v  # Remove volumes
rm -f mock_api/data.db  # Remove SQLite database
rm -f mock_api/mocks.json  # Remove mock registry
docker compose up --build
