#!/usr/bin/env bash
# Creates .env from .env.example, replacing each change-me value with a random one.
set -euo pipefail

if [[ -e .env ]]; then
    echo ".env already exists, leaving it unchanged" >&2
    exit 1
fi

umask 077
while IFS= read -r line; do
    if [[ $line == *=change-me ]]; then
        echo "${line%change-me}$(openssl rand -hex 24)"
    else
        echo "$line"
    fi
done <.env.example >.env
