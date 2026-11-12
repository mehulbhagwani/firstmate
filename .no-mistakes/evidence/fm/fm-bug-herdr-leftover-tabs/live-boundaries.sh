#!/usr/bin/env bash
set -eu
ROOT=$PWD
EVIDENCE=/Users/mehul/.no-mistakes/evidence/01M78TPY1BKYD90R34F82RS9ZK
LAB_HELPER="$ROOT/bin/fm-herdr-lab.sh"
ORIGINAL_PATH=$PATH
unset FM_HOME FM_ROOT_OVERRIDE FM_STATE_OVERRIDE FM_CONFIG_OVERRIDE FM_DATA_OVERRIDE FM_PROJECTS_OVERRIDE FM_BACKEND HERDR_SESSION HERDR_SOCKET_PATH HERDR_PANE_ID HERDR_TAB_ID HERDR_WORKSPACE_ID
LAB_HOME=$(mktemp -d "$ROOT/.cleanup-lab.XXXXXX")
"$ROOT/bin/fm-lab-home.sh" create "$LAB_HOME" >/dev/null
export FM_HERDR_LAB_STATE_DIR="$ROOT/.herdr-test-state"
LAB_SESSION=$("$LAB_HELPER" name guard)
export LAB_HELPER LAB_SESSION ORIGINAL_PATH
cleanup() {
  rc=$?
  env PATH="$ORIGINAL_PATH" "$LAB_HELPER" teardown "$LAB_SESSION" || rc=1
  rm -rf "$LAB_HOME"
  printf 'Lab teardown and fleet-session identity verification exit=%s\n' "$rc"
  exit "$rc"
}
trap cleanup EXIT
"$LAB_HELPER" provision "$LAB_SESSION"
lab() { env PATH="$ORIGINAL_PATH" "$LAB_HELPER" run "$LAB_SESSION" "$@"; }
mkdir -p "$LAB_HOME/bin"
printf 'on\n' > "$LAB_HOME/config/herdr-presentation-spaces"
printf 'herdr\n' > "$LAB_HOME/config/backend"
cat > "$LAB_HOME/bin/herdr" <<'WRAPPER'
#!/usr/bin/env bash
set -eu
args=("$@")
last=$((${#args[@]} - 1)); flag=$((last - 1))
if [ "${#args[@]}" -ge 2 ] && [ "${args[$flag]}" = --session ] && [ "${args[$last]}" = "$LAB_SESSION" ]; then
  unset "args[$last]" "args[$flag]"
fi
for arg in "${args[@]}"; do
  case "$arg" in --session|--session=*) exit 9 ;; esac
done
exec env PATH="$ORIGINAL_PATH" "$LAB_HELPER" run "$LAB_SESSION" "${args[@]}"
WRAPPER
chmod +x "$LAB_HOME/bin/herdr"
export FM_HOME="$LAB_HOME" FM_BACKEND=herdr HERDR_SESSION="$LAB_SESSION"
export PATH="$LAB_HOME/bin:$ORIGINAL_PATH"
"$ROOT/bin/fm-lock.sh"
a=$(lab workspace create --cwd "$ROOT" --label focus-anchor --focus)
at=$(printf '%s' "$a" | jq -r .result.tab.tab_id)
aw=$(printf '%s' "$a" | jq -r .result.workspace.workspace_id)
id=preservation-proof
token=AbCdEfGhIjKlMnOpQrStUv
title="└ $id · p:$token"
c=$(lab workspace create --cwd "$ROOT" --label "$title" --no-focus)
ws=$(printf '%s' "$c" | jq -r .result.workspace.workspace_id)
tab=$(printf '%s' "$c" | jq -r .result.tab.tab_id)
pane=$(printf '%s' "$c" | jq -r .result.root_pane.pane_id)
journal="$FM_HOME/state/$id.herdr-presentation"
write_journal() {
  printf 'version=2\ntask_id=%s\nprojection_id=%s\nhome=%s\nsession=%s\nworkspace_id=%s\ntab_id=%s\npane_id=%s\nparent_workspace_id=%s\nparent_label=focus-anchor\nworkspace_label=%s\ntask_label=fm-%s\n' "$id" "$token" "$FM_HOME" "$LAB_SESSION" "$ws" "$1" "$pane" "$aw" "$title" "$id" > "$journal"
}
snapshot() { lab api snapshot | tee "$EVIDENCE/$1.json"; }
preserve() {
  printf '\nSCENARIO: %s\n' "$1"
  "$ROOT/bin/fm-herdr-session-cleanup.sh"
  lab tab get "$tab"
  [ -f "$journal" ]
  printf 'journal retained\n'
}
write_journal "$tab"
snapshot before-live-boundaries
rc=0
FM_HERDR_SESSION_CLEANUP_SOURCE_ONLY=1 bash -c '. "$1/bin/fm-herdr-session-cleanup.sh"; fm_backend_herdr_projection_close_empty_tab_focus_preserving "$2" "$3" "$4"' _ "$ROOT" "$LAB_SESSION" "$ws" "$tab" || rc=$?
[ "$rc" -ne 0 ]
printf '\nSCENARIO: empty-tab closer refuses a real non-empty tab (exit=%s)\n' "$rc"
lab tab get "$tab"
env PATH="$ORIGINAL_PATH" "$LAB_HELPER" viewer start "$LAB_SESSION"
lab terminal title clear
lab tab focus "$tab"
preserve 'an attached viewer keeps the focused matching v2 projection'
[ "$(lab api snapshot | jq -r .result.snapshot.focused_tab_id)" = "$tab" ]
lab tab focus "$at" >/dev/null
write_journal "$at"
preserve 'a v2 journal bound to a different tab grants no cleanup authority'
write_journal "$tab"
touch "$FM_HOME/state/$id.meta"
preserve 'current task metadata prevents stale cleanup'
rm "$FM_HOME/state/$id.meta"
extra=$(lab tab create --workspace "$ws" --cwd "$ROOT" --label user-tab --no-focus)
et=$(printf '%s' "$extra" | jq -r .result.tab.tab_id)
preserve 'an additional user tab prevents cleanup of the projected workspace'
lab tab get "$et"
snapshot after-live-boundaries
[ "$(lab api snapshot | jq -r .result.snapshot.focused_tab_id)" = "$at" ]
env PATH="$ORIGINAL_PATH" "$LAB_HELPER" viewer stop "$LAB_SESSION"
printf 'All exercised live preservation boundaries passed.\n'
