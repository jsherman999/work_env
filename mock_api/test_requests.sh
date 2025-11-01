#!/usr/bin/env bash
set -euo pipefail
echo "health:" 
curl -sS http://127.0.0.1:8000/health | jq || cat
echo
echo "list first user (simple filter):"
curl -sS "http://127.0.0.1:8000/users?filter=samaccountname=johndoe" | jq || cat
echo
echo "ldap filter (Admins):"
curl -sS "http://127.0.0.1:8000/users?filter=(memberOf=Admins)" | jq || cat
