#!/bin/bash
set -e

# From backend/ root: tear down Compose volumes and rebuild.
docker compose down -v
docker compose up --build
