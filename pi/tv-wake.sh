#!/usr/bin/env bash
# Night watch: while the TV is meant to be off, poll the wall's alerts and switch the TV on for an urgent one.
# Usage: tv-wake.sh http://server:8470/   (run from a user service; exits when the alert list is unreachable
# for ten minutes so systemd restarts it with a fresh connection)
set -uo pipefail
base="${1:?usage: tv-wake.sh http://server:8470/}"
seen=""; fails=0
while true; do
	if json=$(curl -fsS -m 8 "${base%/}/data/alerts.json" 2>/dev/null); then
		fails=0
		id=$(printf '%s' "$json" | python3 -c '
import json,sys,time
now=time.time()
a=[x for x in json.load(sys.stdin) if x.get("level")=="urgent" and x.get("expires",0)>now and now-x.get("created",0)<600]
print(a[-1]["id"] if a else "")' 2>/dev/null)
		if [[ -n $id && $id != "$seen" ]]; then
			seen=$id
			"$(dirname "$0")/tv-power.sh" on
		fi
	else
		(( ++fails >= 20 )) && exit 1
	fi
	sleep 30
done
