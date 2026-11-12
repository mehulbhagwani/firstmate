#!/usr/bin/env bash
set -euo pipefail
RUN_ROOT=$PWD
AREA="$RUN_ROOT/.test-treehouse/live"
EVIDENCE=/Users/mehul/.no-mistakes/evidence/01M78SEHPJYET4JXA0WSA7XZG3
mkdir -p "$AREA" "$AREA/tmp"
export TMPDIR="$AREA/tmp"
. "$RUN_ROOT/tests/git-config-helpers.sh"
unset FM_ROOT_OVERRIDE FM_STATE_OVERRIDE FM_DATA_OVERRIDE FM_CONFIG_OVERRIDE FM_PROJECTS_OVERRIDE FM_ROOT FM_HOME STATE
export FM_HOME="$AREA/north home"
"$RUN_ROOT/bin/fm-lab-home.sh" create "$FM_HOME"
"$RUN_ROOT/bin/fm-lab-home.sh" create "$AREA/south'home"
. "$RUN_ROOT/bin/fm-wake-lib.sh"
git init -q -b main "$AREA/origin"
git -C "$AREA/origin" config user.name 'Pool validation'
git -C "$AREA/origin" config user.email 'pool-validation@example.invalid'
printf 'isolated validation repository\n' > "$AREA/origin/README"
git -C "$AREA/origin" add README
git -C "$AREA/origin" commit -qm fixture
git clone -q "$AREA/origin" "$FM_HOME/projects/project"
git clone -q "$AREA/origin" "$AREA/south'home/projects/project"
CLONE_A="$FM_HOME/projects/project"
CLONE_B="$AREA/south'home/projects/project"
ROOT_A=$(fm_treehouse_home_root "$FM_HOME")
ROOT_B=$(fm_treehouse_home_root "$AREA/south'home")
ln -s "$FM_HOME" "$AREA/alias"
ROOT_ALIAS=$(fm_treehouse_home_root "$AREA/alias")
[ "$ROOT_A" = "$ROOT_ALIAS" ]
[ "$ROOT_A" != "$ROOT_B" ]
printf '\nInstalled provider: '; treehouse --version
printf 'Home A root: %s\nHome B root: %s\nSymlink alias root: %s\n' "$ROOT_A" "$ROOT_B" "$ROOT_ALIAS"
export TREEHOUSE_ROOT="$AREA/unwanted-shared-root"
(cd "$CLONE_A" && treehouse --root "$ROOT_A" get --lease --lease-holder north) > "$AREA/a.path" &
PID_A=$!
(cd "$CLONE_B" && treehouse --root "$ROOT_B" get --lease --lease-holder south) > "$AREA/b.path" &
PID_B=$!
wait "$PID_A"
wait "$PID_B"
WT_A=$(cat "$AREA/a.path")
WT_B=$(cat "$AREA/b.path")
printf '\nConcurrent acquisitions with an ambient shared TREEHOUSE_ROOT:\nA=%s\nB=%s\n' "$WT_A" "$WT_B"
[ ! -e "$TREEHOUSE_ROOT" ]
[ "$(git -C "$WT_A" rev-parse --git-common-dir)" = "$CLONE_A/.git" ]
[ "$(git -C "$WT_B" rev-parse --git-common-dir)" = "$CLONE_B/.git" ]
git -C "$CLONE_A" worktree list --porcelain
git -C "$CLONE_B" worktree list --porcelain
(cd "$CLONE_A" && treehouse --root "$ROOT_A" status --json) | tee "$EVIDENCE/north-pool.json"
(cd "$CLONE_B" && treehouse --root "$ROOT_B" status --json) | tee "$EVIDENCE/south-pool.json"
printf '\nInteractive acquisition through the canonical alias root:\n'
ENTERED=$(cd "$CLONE_A" && printf 'pwd -P\nexit\n' | treehouse --root "$ROOT_ALIAS" get)
printf '%s\n' "$ENTERED"
printf '%s\n' "$ENTERED" | grep -F "$ROOT_A/"
LEGACY=$(cd "$CLONE_A" && treehouse --root "$AREA/legacy" get --lease --lease-holder legacy)
printf '\nReturn a legacy lease after switching the allocation root:\nLegacy path: %s\n' "$LEGACY"
(cd "$CLONE_A" && treehouse --root "$ROOT_A" return --force "$LEGACY")
AGAIN=$(cd "$CLONE_A" && treehouse --root "$AREA/legacy" get --lease --lease-holder recheck)
[ "$AGAIN" = "$LEGACY" ]
printf 'Reacquired the same legacy slot: %s\n' "$AGAIN"
(cd "$CLONE_A" && treehouse return --force "$AGAIN")
(cd "$CLONE_A" && treehouse return --force "$WT_A")
export TREEHOUSE_ROOT="$AREA/legacy/.treehouse"
printf '\nStartup diagnostics without the pool-report opt-in:\n'
FM_BOOTSTRAP_DETECT_ONLY=1 FM_BOOTSTRAP_NETWORK=skip "$RUN_ROOT/bin/fm-bootstrap.sh" > "$AREA/report-off.log"
cat "$AREA/report-off.log"
! grep -q TREEHOUSE_POOL_REPORT "$AREA/report-off.log"
touch "$FM_HOME/config/treehouse-pool-report"
find "$ROOT_A" "$ROOT_B" "$AREA/legacy" -name treehouse-state.json -exec shasum -a 256 {} \; | sort > "$AREA/before.sha"
printf '\nStartup diagnostics with pool reporting enabled and a zero-day age threshold:\n'
FM_POOL_ORPHAN_DAYS=0 FM_BOOTSTRAP_DETECT_ONLY=1 FM_BOOTSTRAP_NETWORK=skip "$RUN_ROOT/bin/fm-bootstrap.sh" > "$AREA/report-on.log"
cat "$AREA/report-on.log"
grep -F "unowned slot older than 0d: $WT_A" "$AREA/report-on.log"
grep -F "unowned slot older than 0d: $LEGACY" "$AREA/report-on.log"
! grep -F "$WT_B" "$AREA/report-on.log"
find "$ROOT_A" "$ROOT_B" "$AREA/legacy" -name treehouse-state.json -exec shasum -a 256 {} \; | sort > "$AREA/after.sha"
cmp "$AREA/before.sha" "$AREA/after.sha"
printf 'Pool state digests are unchanged by diagnostics.\n'
printf '\nMalformed parent binding refuses root resolution:\n'
printf 'schema=not-a-parent-record\n' > "$FM_HOME/.fm-secondmate-parent"
if fm_treehouse_home_root "$FM_HOME" > "$AREA/invalid.out" 2> "$AREA/invalid.err"; then
  echo 'ERROR: accepted a malformed parent record'; exit 1
fi
cat "$AREA/invalid.err"
[ ! -s "$AREA/invalid.out" ]
printf 'No allocation root was returned.\n'
rm "$FM_HOME/.fm-secondmate-parent"
printf '\nLive evidence collection complete.\n'
