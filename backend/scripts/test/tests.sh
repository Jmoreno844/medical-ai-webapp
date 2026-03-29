#!/bin/bash
set -e

echo "Running tests..."
python -m pytest -v --no-migrations "$@"
