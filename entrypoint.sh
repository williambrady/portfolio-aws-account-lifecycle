#!/bin/bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}=== AWS Account Lifecycle ===${NC}" >&2

# Read profiles from config.yaml if env vars not set
if [ -z "${MGMT_PROFILE:-}" ] && [ -f config.yaml ]; then
    MGMT_PROFILE=$(python3 -c "import yaml; c=yaml.safe_load(open('config.yaml')); print(c.get('mgmt_profile',''))" 2>/dev/null || true)
fi
if [ -z "${AUTOMATION_PROFILE:-}" ] && [ -f config.yaml ]; then
    AUTOMATION_PROFILE=$(python3 -c "import yaml; c=yaml.safe_load(open('config.yaml')); print(c.get('automation_profile',''))" 2>/dev/null || true)
fi

# Validate AWS credentials using automation profile if set, otherwise default
VALIDATE_PROFILE="${AUTOMATION_PROFILE:-${MGMT_PROFILE:-}}"
if [ -n "$VALIDATE_PROFILE" ]; then
    echo "Validating AWS credentials (profile: ${VALIDATE_PROFILE})..." >&2
    if ! aws sts get-caller-identity --profile "$VALIDATE_PROFILE" >&2 2>&1; then
        echo -e "${RED}ERROR: AWS credentials not configured or invalid for profile: ${VALIDATE_PROFILE}${NC}" >&2
        echo "Mount your AWS credentials: -v \"\$HOME/.aws:/home/lifecycle/.aws:ro\"" >&2
        exit 1
    fi
else
    echo "Validating AWS credentials..." >&2
    if ! aws sts get-caller-identity >&2 2>&1; then
        echo -e "${RED}ERROR: AWS credentials not configured or invalid${NC}" >&2
        echo "Mount your AWS credentials: -v \"\$HOME/.aws:/home/lifecycle/.aws:ro\"" >&2
        exit 1
    fi
fi
echo "" >&2

exec python3 -m src.main "$@"
