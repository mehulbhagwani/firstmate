#!/usr/bin/env bash
set -euo pipefail
RUN_ROOT=$PWD
AREA="$RUN_ROOT/.test-treehouse/seed-live"
CODE="$RUN_ROOT/.test-treehouse/seed-code"
mkdir -p "$AREA/tmp"
export TMPDIR="$AREA/tmp"
. "$RUN_ROOT/tests/git-config-helpers.sh"
unset FM_HOME FM_ROOT FM_ROOT_OVERRIDE FM_STATE_OVERRIDE FM_DATA_OVERRIDE FM_CONFIG_OVERRIDE FM_PROJECTS_OVERRIDE STATE
for side in north south; do
  parent="$AREA/$side"
  "$RUN_ROOT/bin/fm-lab-home.sh" create "$parent"
  printf '\nSeed a leased secondmate from %s:\n' "$side"
  FM_HOME="$parent" FM_ROOT_OVERRIDE="$CODE" \
    FM_SECONDMATE_CHARTER='Disposable pool-validation home with no assigned work.' \
    FM_SECONDMATE_SCOPE='Pool validation only' \
    "$CODE/bin/fm-home-seed.sh" "$side-child" - --no-projects > "$AREA/$side.out"
  cat "$AREA/$side.out"
  child=$(sed -n 's/^home=//p' "$AREA/$side.out")
  [ -d "$child" ]
  printf 'Persisted parent binding:\n'
  cat "$child/.fm-secondmate-parent"
  printf 'Persisted registry:\n'
  cat "$parent/data/secondmates.md"
  root=$(FM_HOME="$parent" FM_ROOT_OVERRIDE="$CODE" bash -c '. "$1/bin/fm-wake-lib.sh"; fm_treehouse_home_root "$FM_HOME"' _ "$CODE")
  case "$child" in "$root"/*) ;; *) exit 1 ;; esac
  child_root=$(FM_HOME="$child" FM_ROOT_OVERRIDE="$CODE" bash -c '. "$1/bin/fm-wake-lib.sh"; fm_treehouse_home_root "$FM_HOME"' _ "$CODE")
  case "$child_root" in "$AREA/.firstmate-worktrees/"*) ;; *) exit 1 ;; esac
  [ "$root" != "$child_root" ]
  printf 'Parent pool root: %s\nChild pool root: %s\n' "$root" "$child_root"
  (cd "$CODE" && treehouse --root "$root" status --json)
  printf '%s\n' "$child" > "$AREA/$side.path"
done
[ "$(cat "$AREA/north.path")" != "$(cat "$AREA/south.path")" ]
printf '\nBoth parent homes seeded separate, durable leased homes from one source repository.\n'
