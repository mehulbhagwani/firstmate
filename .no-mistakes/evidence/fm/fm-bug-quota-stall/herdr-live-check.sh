#!/usr/bin/env bash
set -euo pipefail
ROOT=$PWD
EVIDENCE=/Users/mehul/.no-mistakes/evidence/01M7B7WG3BCHA3HSBDJ3M5GQZ2
LAB=$(mktemp -d "$ROOT/.quota-herdr.XXXXXX")
HERDR_LAB_HELPER="$ROOT/bin/fm-herdr-lab.sh"
HERDR_ORIGINAL_PATH=$PATH
export HERDR_LAB_HELPER HERDR_ORIGINAL_PATH
export FM_HERDR_LAB_STATE_DIR="$LAB/herdr-state"
HERDR_LAB_SESSION=$("$HERDR_LAB_HELPER" name quota-stall)
export HERDR_LAB_SESSION
cleanup() {
  code=$?
  if [ -f "$FM_HERDR_LAB_STATE_DIR/$HERDR_LAB_SESSION.fleet-state.json" ]; then
    env PATH="$HERDR_ORIGINAL_PATH" "$HERDR_LAB_HELPER" teardown "$HERDR_LAB_SESSION" || code=1
  fi
  if [ "$code" = 0 ]; then
    printf 'Herdr lab removed; default-session tripwire unchanged.\n'
  fi
  rm -rf "$LAB"
  exit "$code"
}
trap cleanup EXIT
unset NO_MISTAKES_GATE FM_GATE_REFUSE_BYPASS FM_ROOT_OVERRIDE FM_STATE_OVERRIDE FM_DATA_OVERRIDE FM_CONFIG_OVERRIDE FM_PROJECTS_OVERRIDE FM_CREW_STATE_META_OVERRIDE FM_CREW_STATE_STATUS_OVERRIDE HERDR_PANE_ID HERDR_WORKSPACE_ID HERDR_TAB_ID HERDR_SESSION
"$ROOT/bin/fm-lab-home.sh" create "$LAB"
export FM_HOME="$LAB" FM_BACKEND=herdr FM_CREW_STATE_NO_FORGE=1
mkdir -p "$LAB/project" "$LAB/pi" "$LAB/transport"
# Provision performs prepare before starting the named non-default server.
"$HERDR_LAB_HELPER" provision "$HERDR_LAB_SESSION"
cat > "$LAB/transport/herdr" <<'SH'
#!/usr/bin/env bash
set -eu
args=("$@")
last=$((${#args[@]} - 1))
flag=$((last - 1))
if [ "${#args[@]}" -ge 2 ] && [ "${args[$flag]}" = --session ] && [ "${args[$last]}" = "$HERDR_LAB_SESSION" ]; then
  unset 'args[last]' 'args[flag]'
fi
for arg in "${args[@]}"; do
  case "$arg" in --session|--session=*) exit 9 ;; esac
done
exec env PATH="$HERDR_ORIGINAL_PATH" "$HERDR_LAB_HELPER" run "$HERDR_LAB_SESSION" "${args[@]}"
SH
chmod +x "$LAB/transport/herdr"
export PATH="$LAB/transport:$HERDR_ORIGINAL_PATH"
lab() { env PATH="$HERDR_ORIGINAL_PATH" "$HERDR_LAB_HELPER" run "$HERDR_LAB_SESSION" "$@"; }
classify() { bash -c '. "$1/bin/fm-backend.sh"; fm_backend_agent_state herdr "$2"' _ "$ROOT" "$HERDR_LAB_SESSION:$1"; }
wait_state() {
  local pane=$1 expected=$2 i state
  for ((i=0; i<100; i++)); do
    state=$(classify "$pane")
    [ "$state" = "$expected" ] && { printf '%s process classification: %s\n' "$pane" "$state"; return; }
    sleep .2
  done
  printf 'Expected %s; observed %s\n' "$expected" "$state"
  lab agent get "$pane" || true
  lab pane read "$pane" --source recent --lines 100 || true
  exit 1
}
assert_output() {
  printf '%s\n%s\n' "$1" "$3"
  [[ "$3" == *"$2"* ]] || { printf 'FAILED expected: %s\n' "$2"; exit 1; }
}
write_meta() {
  printf 'window=%s:%s\nworktree=%s\nkind=scout\nbackend=herdr\nharness=pi\n' "$HERDR_LAB_SESSION" "$2" "$LAB/project" > "$LAB/state/$1.meta"
  printf 'working: last turn before the agent exits\n' > "$LAB/state/$1.status"
  "$ROOT/bin/fm-busy-event.sh" arm "$LAB/state" "$1" --source pi-ext --event user-prompt-submit >/dev/null
}
created=$(lab workspace create --cwd "$LAB/project" --label quota-lab --no-focus)
P_EXIT=$(printf '%s' "$created" | jq -er '.result.root_pane.pane_id')
WS=$(printf '%s' "$created" | jq -er '.result.workspace.workspace_id')
created=$(lab tab create --workspace "$WS" --cwd "$LAB/project" --label live-sibling --no-focus)
P_LIVE=$(printf '%s' "$created" | jq -er '.result.root_pane.pane_id // .result.pane.pane_id')
# A nested shell reproduces the retained registration shape after Pi exits.
lab pane run "$P_EXIT" '/bin/zsh -f' >/dev/null
sleep 1
printf -v launch 'env PI_CODING_AGENT_DIR=%q PI_TELEMETRY=0 pi --offline --no-approve --no-mcp --no-skills --no-context-files --no-prompt-templates --no-themes --no-session --no-tools --tui-mode regular' "$LAB/pi"
lab pane run "$P_EXIT" "$launch" >/dev/null
lab pane run "$P_LIVE" "$launch" >/dev/null
wait_state "$P_EXIT" alive
wait_state "$P_LIVE" alive
write_meta exited "$P_EXIT"
write_meta live "$P_LIVE"
assert_output 'Pi before exit is working' 'state: working' "$("$ROOT/bin/fm-crew-state.sh" exited)"
assert_output 'Sibling Pi is working' 'state: working' "$("$ROOT/bin/fm-crew-state.sh" live)"
lab pane process-info --pane "$P_EXIT" > "$EVIDENCE/herdr-before-process.json"
lab agent get "$P_EXIT" > "$EVIDENCE/herdr-before-agent.json"
lab pane send-text "$P_EXIT" /quit >/dev/null
sleep .5
lab pane send-keys "$P_EXIT" Enter >/dev/null
sleep 1
lab pane send-keys "$P_EXIT" Enter >/dev/null
wait_state "$P_EXIT" dead
lab pane process-info --pane "$P_EXIT" > "$EVIDENCE/herdr-after-process.json"
lab agent get "$P_EXIT" > "$EVIDENCE/herdr-after-agent.json" || true
printf 'Herdr registration after exit:\n'
cat "$EVIDENCE/herdr-after-agent.json"
assert_output 'Exited Pi with stale busy record is agent gone' 'agent gone, pane shell remains' "$("$ROOT/bin/fm-crew-state.sh" exited)"
"$ROOT/bin/fm-busy-event.sh" apply "$LAB/state" exited idle --current-gen --source pi-ext --event stop
assert_output 'Exited Pi with stale idle record and working event is agent gone' 'agent gone, pane shell remains' "$("$ROOT/bin/fm-crew-state.sh" exited)"
assert_output 'The sibling remains working after the other Pi exits' 'state: working' "$("$ROOT/bin/fm-crew-state.sh" live)"
for verb in done failed; do
  printf '%s: terminal result before exit\n' "$verb" > "$LAB/state/exited.status"
  assert_output "Exited Herdr worker preserves $verb" "state: $verb" "$("$ROOT/bin/fm-crew-state.sh" exited)"
done
printf 'All live Herdr scenarios passed.\n'
