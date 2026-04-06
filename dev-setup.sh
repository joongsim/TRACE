#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "🐘 Starting database container..."
docker compose up -d postgres

# Optional: Wait for postgres to be ready before migrating
echo "⏳ Waiting for database to be ready..."
until docker compose exec postgres pg_isready -U trace > /dev/null 2>&1; do
  sleep 1
done

echo "📦 Syncing Python dependencies with uv..."
uv sync --all-extras

echo "🚀 Running database migrations..."
make migrate

echo "🧪 Running tests..."
make test

echo "✨ Linting code..."
make lint

echo "✅ Environment is ready for development!"