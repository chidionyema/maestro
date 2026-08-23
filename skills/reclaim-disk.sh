#!/bin/bash
# Reclaim disk space from caches that regenerate themselves.
#
# maestro recorded 33 disk-exhaustion incidents between 16:18 and 18:02 on
# 2026-08-23 and handed every one of them to the founder, because it had no
# skill for the shape. This is that skill.
#
# What it will delete: only things a machine rebuilds on its own, and only
# under $HOME. Package manager caches, Xcode's DerivedData, its own old logs.
# What it will never delete: source, documents, databases, virtualenvs, model
# weights, anything under iCloud Drive, anything it did not put there. The
# HuggingFace cache is deliberately excluded: it regenerates, but over a
# network connection and several gigabytes at a time, which is a cost, not a
# reclaim.
#
#   reclaim-disk.sh --check    say what it would free, delete nothing, exit 0
#   reclaim-disk.sh            free it, then prove the free space moved
#
# Exit 0 means the disk ended above the critical threshold. Exit 1 means it did
# not, and a person needs to look, which is the honest outcome when the thing
# eating the disk is not a cache.

set -uo pipefail

CRITICAL_GB="${MAESTRO_DISK_CRITICAL_GB:-5}"
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

free_gb() { df -g / | awk 'NR==2 {print $4}'; }

# path, then a human name. Order is cheapest-to-regenerate first.
TARGETS=(
  "$HOME/Library/Caches/pip|pip cache"
  "$HOME/.cache/pip|pip cache"
  "$HOME/Library/Caches/Homebrew|Homebrew downloads"
  "$HOME/.npm/_cacache|npm cache"
  "$HOME/Library/Developer/Xcode/DerivedData|Xcode DerivedData"
  "$HOME/Library/Caches/go-build|Go build cache"
  "$HOME/.cargo/registry/cache|Cargo registry cache"
)

BEFORE=$(free_gb)
echo "free before: ${BEFORE} GiB (critical below ${CRITICAL_GB})"

TOTAL_MB=0
for entry in "${TARGETS[@]}"; do
  path="${entry%%|*}"; name="${entry##*|}"
  [ -d "$path" ] || continue
  # Refuse anything that is not squarely inside $HOME, however it got here.
  case "$path" in "$HOME"/*) ;; *) echo "  refused, outside HOME: $path"; continue ;; esac
  mb=$(du -sm "$path" 2>/dev/null | awk '{print $1}')
  [ -z "$mb" ] && continue
  TOTAL_MB=$((TOTAL_MB + mb))
  if [ "$CHECK" = "1" ]; then
    printf "  would free %6s MB  %s\n" "$mb" "$name"
  else
    rm -rf -- "${path:?}"/* 2>/dev/null
    printf "  freed      %6s MB  %s\n" "$mb" "$name"
  fi
done

# Its own logs, older than 30 days. maestro writes these; maestro may remove them.
if [ "$CHECK" = "1" ]; then
  n=$(find "$HOME/.maestro" -name "*.log*" -mtime +30 2>/dev/null | wc -l | tr -d ' ')
  echo "  would delete ${n} maestro log file(s) older than 30 days"
else
  find "$HOME/.maestro" -name "*.log*" -mtime +30 -delete 2>/dev/null
fi

if [ "$CHECK" = "1" ]; then
  echo "reclaimable: ~${TOTAL_MB} MB. Nothing was deleted."
  exit 0
fi

AFTER=$(free_gb)
echo "free after:  ${AFTER} GiB (was ${BEFORE})"

if [ "$AFTER" -ge "$CRITICAL_GB" ]; then
  echo "disk is above the critical threshold"
  exit 0
fi
echo "still below ${CRITICAL_GB} GiB after clearing every cache: the disk is being"
echo "eaten by something that is not a cache, and a person needs to look"
exit 1
