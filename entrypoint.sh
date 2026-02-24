#!/bin/bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}=== AWS Account Lifecycle ===${NC}" >&2

# Validate AWS credentials
echo "Validating AWS credentials..." >&2
if ! aws sts get-caller-identity >&2 2>&1; then
    echo -e "${RED}ERROR: AWS credentials not configured or invalid${NC}" >&2
    echo "Mount your AWS credentials: -v \"\$HOME/.aws:/home/lifecycle/.aws:ro\"" >&2
    exit 1
fi
echo "" >&2

exec python3 -m src.main "$@"
