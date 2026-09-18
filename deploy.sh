#!/usr/bin/env bash
# Root quick deployment shortcut
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/infra/deploy/deploy_code.sh" "$@"

