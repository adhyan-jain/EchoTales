#!/usr/bin/env bash
# Run a command; kill it by PID if available RAM drops under 1.5 GB (the machine has 15 GB; ollama spill can spike).
"$@" &
PID=$!
while kill -0 "$PID" 2>/dev/null; do
  AVAIL=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
  if [ "$AVAIL" -lt 1500 ]; then echo "RAM guard: ${AVAIL} MB available, killing $PID" >&2; kill "$PID"; break; fi
  sleep 5
done
wait "$PID"
