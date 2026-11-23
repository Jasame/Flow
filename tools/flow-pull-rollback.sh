#!/bin/bash
# Undo a flow-pull.sh deploy: put back the files it replaced, remove the ones it added, restart.
# The database is left as it is (migrations only add tables/columns); a copy from before the deploy
# is in <backup dir>/flow-before.sqlite3 if it is ever needed.
# usage: flow-pull-rollback.sh <backup dir printed by flow-pull.sh>
# The 内测版: FLOW_SERVICE=flow-beta FLOW_URL=http://127.0.0.1:8092 (flow-pull.sh passes them on).
set -u
BK=$1; SVC=${FLOW_SERVICE:-flow}; U=${FLOW_URL:-http://127.0.0.1:8090}
[ -d "$BK/files" ] && [ -f "$BK/new-files.txt" ] || { echo "not a flow-pull backup: $BK"; exit 1; }
(cd "$BK/files" && find . -type f | while read -r f; do cp -p "$f" "/${f#./}"; done)
while read -r n; do [ -n "$n" ] && rm -f "$n"; done < "$BK/new-files.txt"
systemctl restart "$SVC"; sleep 5
echo "rolled back: $(systemctl is-active "$SVC") health=$(curl -s -m 15 -o /dev/null -w '%{http_code}' "$U/api/health")"
