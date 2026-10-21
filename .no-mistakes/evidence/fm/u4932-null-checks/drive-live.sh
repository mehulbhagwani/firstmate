#!/usr/bin/env bash
# Usage: drive-live.sh <worktree-root> <case-name> <pr-url> [extra fm-pr-merge args]
# Runs the real bin/fm-pr-merge.sh in a disposable lab home against real GitHub,
# with a guard gh/gh-axi on PATH that refuses every mutation locally.
set -u
EV=$(cd "$(dirname "$0")" && pwd); ROOT=$1; NAME=$2; URL=$3; shift 3
LAB=$(mktemp -d "${TMPDIR:-/tmp}/fm-lab.XXXXXX")
env -u FM_ROOT_OVERRIDE -u FM_STATE_OVERRIDE "$ROOT/bin/fm-lab-home.sh" create "$LAB" >/dev/null
mkdir -p "$LAB/wt"
printf 'window=fm-live\nkind=ship\nmode=no-mistakes\nworktree=%s\nproject=%s\n' "$LAB/wt" "$LAB/wt" > "$LAB/state/live-x1.meta"
OUT="$EV/$NAME"; mkdir -p "$OUT"; : > "$OUT/gh-calls.log"
printf '%s %s %s\n' "$ROOT/bin/fm-pr-merge.sh" live-x1 "$URL $*" > "$OUT/command.txt"
env -u FM_ROOT_OVERRIDE -u FM_STATE_OVERRIDE -u FM_DATA_OVERRIDE -u FM_CONFIG_OVERRIDE -u FM_PROJECTS_OVERRIDE \
  FM_HOME="$LAB" FM_GUARD_LOG="$OUT/gh-calls.log" PATH="$EV/guard-bin:$PATH" \
  "$ROOT/bin/fm-pr-merge.sh" live-x1 "$URL" "$@" > "$OUT/stdout" 2> "$OUT/stderr"
echo $? > "$OUT/exit"
rm -rf "$LAB"
echo "== $NAME exit=$(cat "$OUT/exit")"; cat "$OUT/stderr" "$OUT/stdout"; echo "-- refused:"; grep GUARD-REFUSED "$OUT/gh-calls.log"
