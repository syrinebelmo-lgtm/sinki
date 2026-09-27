#!/bin/bash
# Wait until no other Overpass catalog client is running, then nightlife NA-ZZ only.
set -u
cd /Users/syrinebelmo/sinki || exit 1

LOG="${LOG:-/tmp/catalog_nz.log}"
exec >>"$LOG" 2>&1

PYTHON="/Users/syrinebelmo/sinki/.venv/bin/python3"
if [ ! -x "$PYTHON" ]; then
  PYTHON="/Users/syrinebelmo/sinki/venv/bin/python3"
fi
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi

echo "$(date '+%Y-%m-%dT%H:%M:%S') waiter pid=$$ using $PYTHON; waiting while int_catalog or nightlife AA-MZ still runs"

overpass_busy() {
  local err
  err=$(pgrep -f int_catalog 2>&1 >/dev/null)
  if [ $? -eq 0 ]; then
    return 0
  fi
  case "$err" in
    *Cannot\ get\ process\ list*|*sysmon*) return 0 ;;
  esac
  err=$(pgrep -f 'france_nightlife --catalog AA' 2>&1 >/dev/null)
  if [ $? -eq 0 ]; then
    return 0
  fi
  case "$err" in
    *Cannot\ get\ process\ list*|*sysmon*) return 0 ;;
  esac
  err=$(pgrep -f 'france_nightlife --catalog --cc-from AA' 2>&1 >/dev/null)
  if [ $? -eq 0 ]; then
    return 0
  fi
  case "$err" in
    *Cannot\ get\ process\ list*|*sysmon*) return 0 ;;
  esac
  return 1
}

while overpass_busy; do
  sleep 60
done

if "$PYTHON" -c "import pipeline.world_places" 2>/dev/null; then
  echo "$(date '+%Y-%m-%dT%H:%M:%S') Overpass free; starting world_places NA-ZZ"
  "$PYTHON" -m pipeline.world_places --catalog --cc-from NA --cc-to ZZ --radius-m 14000
  echo "$(date '+%Y-%m-%dT%H:%M:%S') world_places NA-ZZ done; starting france_nightlife NA-ZZ"
else
  echo "$(date '+%Y-%m-%dT%H:%M:%S') Overpass free; world_places module missing; skip; starting france_nightlife NA-ZZ only"
fi
"$PYTHON" -m pipeline.france_nightlife --catalog --cc-from NA --cc-to ZZ --radius-m 12000
echo "$(date '+%Y-%m-%dT%H:%M:%S') france_nightlife NA-ZZ done"
