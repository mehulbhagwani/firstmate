#!/usr/bin/env bash
set -eu
ROOT=$1
EVIDENCE=$(cd "$(dirname "$0")" && pwd)
SCRATCH=$(mktemp -d "$ROOT/.fm-null-baseline.XXXXXX")
trap 'rm -rf -- "$SCRATCH"' EXIT
git -C "$ROOT" show 427056c4181c41074ad24f051f79919330df0fa5:bin/fm-pr-lib.sh > "$SCRATCH/fm-pr-lib.sh"
export FM_VALIDATION_REAL_GH
FM_VALIDATION_REAL_GH=$(command -v gh)
export FM_VALIDATION_BRANCH_SHAPE=null
for version in base target; do
  OUT="$EVIDENCE/null-$version-reader"
  mkdir -p "$OUT"
  export FM_VALIDATION_OUTPUT="$OUT"
  if [ "$version" = base ]; then LIB="$SCRATCH/fm-pr-lib.sh"; else LIB="$ROOT/bin/fm-pr-lib.sh"; fi
  PATH="$EVIDENCE/guard-bin:$PATH" bash -c '
    . "$1"
    PR_OWNER=cli PR_REPO=cli
    rc=0
    github_read_required_contexts trunk || rc=$?
    printf "reader exit=%s\nrequired=%s\nerror=%s\n" "$rc" "$FM_PR_GITHUB_REQUIRED" "$FM_PR_GITHUB_REQUIRED_ERROR"
    if [ "$2" = base ]; then [ "$rc" = 1 ]; else [ "$rc" = 0 ]; fi
  ' _ "$LIB" "$version" > "$OUT/result.txt"
  cat "$OUT/result.txt"
done
