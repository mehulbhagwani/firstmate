#!/usr/bin/env bash
set -eu
ROOT=$1
EVIDENCE=$(cd "$(dirname "$0")" && pwd)
NAME=$2
URL=$3
SHAPE=${4:-live}
SURFACE=${5:-merge}
export FM_VALIDATION_HIDE_CHECK=${6:-}
OUT="$EVIDENCE/$NAME"
mkdir -p "$OUT"
LAB=$(mktemp -d "$ROOT/.fm-null-validation.XXXXXX")
trap 'rm -rf -- "$LAB"' EXIT
export FM_VALIDATION_REAL_GH
FM_VALIDATION_REAL_GH=$(command -v gh)
export FM_VALIDATION_OUTPUT="$OUT" FM_VALIDATION_BRANCH_SHAPE="$SHAPE"
env -u FM_ROOT_OVERRIDE -u FM_STATE_OVERRIDE "$ROOT/bin/fm-lab-home.sh" create "$LAB" >/dev/null
mkdir -p "$LAB/wt"
printf 'window=fm-live\nkind=ship\nmode=no-mistakes\nworktree=%s\nproject=%s\npr=%s\n' "$LAB/wt" "$LAB/wt" "$URL" > "$LAB/state/live-x1.meta"
if [ "$SURFACE" = park ]; then
  set -- "$ROOT/bin/fm-park.sh" gate live-x1
else
  set -- "$ROOT/bin/fm-pr-merge.sh" live-x1 "$URL"
fi
printf '%q ' "$@" > "$OUT/command.txt"
printf '\nbranch shape: %s\n' "$SHAPE" >> "$OUT/command.txt"
printf 'hidden reported check: %s\n' "$FM_VALIDATION_HIDE_CHECK" >> "$OUT/command.txt"
rc=0
env -u FM_ROOT_OVERRIDE -u FM_STATE_OVERRIDE -u FM_DATA_OVERRIDE -u FM_CONFIG_OVERRIDE -u FM_PROJECTS_OVERRIDE -u FM_GATE_REFUSE_BYPASS -u FM_SUPERVISION_ACTOR \
  FM_HOME="$LAB" PATH="$EVIDENCE/guard-bin:$PATH" "$@" > "$OUT/stdout.txt" 2> "$OUT/stderr.txt" || rc=$?
printf '%s\n' "$rc" > "$OUT/exit.txt"
printf 'Scenario: %s; branch shape: %s; exit: %s\n' "$NAME" "$SHAPE" "$rc"
cat "$OUT/stdout.txt" "$OUT/stderr.txt"
