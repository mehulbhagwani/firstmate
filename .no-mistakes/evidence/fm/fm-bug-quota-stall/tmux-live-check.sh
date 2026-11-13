#!/usr/bin/env bash
set -euo pipefail
ROOT=$PWD
EVIDENCE=/Users/mehul/.no-mistakes/evidence/01M7B7WG3BCHA3HSBDJ3M5GQZ2
LAB=$(mktemp -d "$ROOT/.quota-lab.XXXXXX")
BASELINE="$ROOT/bin/.quota-baseline-$$.sh"
SOCKET_DIR=
cleanup() {
  code=$?
  if [ -n "$SOCKET_DIR" ]; then
    TMUX_TMPDIR="$SOCKET_DIR" tmux -L fm-lab kill-server 2>/dev/null || true
    "$ROOT/bin/fm-lab-home.sh" teardown "$LAB" || code=1
  fi
  rm -f "$BASELINE"
  rm -rf "$LAB"
  printf 'Lab cleanup completed; exit=%s\n' "$code"
  exit "$code"
}
trap cleanup EXIT
unset NO_MISTAKES_GATE FM_GATE_REFUSE_BYPASS FM_ROOT_OVERRIDE FM_STATE_OVERRIDE FM_DATA_OVERRIDE FM_CONFIG_OVERRIDE FM_PROJECTS_OVERRIDE FM_CREW_STATE_META_OVERRIDE FM_CREW_STATE_STATUS_OVERRIDE
"$ROOT/bin/fm-lab-home.sh" create "$LAB"
SOCKET_DIR=$("$ROOT/bin/fm-lab-home.sh" tmux-dir "$LAB")
export TMUX_TMPDIR="$SOCKET_DIR" FM_HOME="$LAB" FM_BACKEND=tmux FM_CREW_STATE_NO_FORGE=1 FM_CREW_STATE_NM_TIMEOUT=1
mkdir -p "$LAB/project" "$LAB/pi"
tmux -f /dev/null -L fm-lab new-session -d -s primary -n worker -x 120 -y 40 -c "$ROOT" -e FM_HOME="$LAB" '/bin/bash --noprofile --norc'
tmux -L fm-lab set-window-option -t primary:worker automatic-rename off >/dev/null
export TMUX
TMUX=$(tmux -L fm-lab display-message -p -t primary:worker '#{socket_path},#{pid},0')
TARGET=primary:worker
ID=quota-worker
write_meta() {
  printf 'window=%s\nworktree=%s\nkind=%s\nbackend=tmux\nharness=pi\nmode=%s\n' "$TARGET" "$LAB/project" "$1" "${2:-no-mistakes}" > "$LAB/state/$ID.meta"
}
write_status() { printf '%s\n' "$1" > "$LAB/state/$ID.status"; }
read_state() { "$ROOT/bin/fm-crew-state.sh" "$ID"; }
assert_output() {
  local label=$1 expected=$2 output=$3
  printf '%s\n%s\n' "$label" "$output"
  [[ "$output" == *"$expected"* ]] || { printf 'FAILED expected: %s\n' "$expected"; exit 1; }
}
backend_state() { bash -c '. "$1/bin/fm-backend.sh"; fm_backend_agent_state tmux "$2"' _ "$ROOT" "$TARGET"; }
wait_state() {
  local expected=$1 state i
  for ((i=0; i<100; i++)); do
    state=$(backend_state)
    [ "$state" = "$expected" ] && { printf 'Real process classification: %s\n' "$state"; return; }
    sleep .2
  done
  printf 'Timed out waiting for %s; observed %s\n' "$expected" "$state"
  tmux -L fm-lab capture-pane -p -t "$TARGET"
  exit 1
}
write_meta scout
write_status 'working: started before the agent exited'
GEN=$("$ROOT/bin/fm-busy-event.sh" arm "$LAB/state" "$ID")
printf 'Launching installed Pi, offline and without a model prompt; isolated config and no tools.\n'
printf -v launch 'PI_CODING_AGENT_DIR=%q PI_TELEMETRY=0 pi --offline --no-approve --no-extensions --no-mcp --no-skills --no-context-files --no-prompt-templates --no-themes --no-session --no-tools --tui-mode regular' "$LAB/pi"
tmux -L fm-lab send-keys -t "$TARGET" -l "$launch"
tmux -L fm-lab send-keys -t "$TARGET" Enter
wait_state alive
sleep 2
tmux -L fm-lab capture-pane -p -t "$TARGET" > "$EVIDENCE/pi-live-pane.txt"
printf 'Live foreground command: %s\n' "$(tmux -L fm-lab display-message -p -t "$TARGET" '#{pane_current_command}')"
"$ROOT/bin/fm-busy-event.sh" apply "$LAB/state" "$ID" busy --gen "$GEN" --source pi-ext --event user-prompt-submit
assert_output 'Live Pi retains busy activity' 'state: working' "$(read_state)"
"$ROOT/bin/fm-busy-event.sh" apply "$LAB/state" "$ID" idle --gen "$GEN" --source pi-ext --event stop
write_status 'needs-decision: waiting for a user answer'
assert_output 'Live idle Pi retains its open decision' 'state: parked' "$(read_state)"
tmux -L fm-lab new-window -d -t primary -n sibling -c "$ROOT" '/bin/bash --noprofile --norc'
tmux -L fm-lab set-window-option -t primary:sibling automatic-rename off >/dev/null
tmux -L fm-lab send-keys -t primary:sibling -l "$launch"
tmux -L fm-lab send-keys -t primary:sibling Enter
TARGET=primary:sibling
wait_state alive
ID=live-sibling
write_meta scout
write_status 'working: independent sibling agent'
"$ROOT/bin/fm-busy-event.sh" arm "$LAB/state" "$ID" --source pi-ext --event user-prompt-submit >/dev/null
TARGET=primary:worker
ID=quota-worker
write_status 'working: started before the agent exited'
tmux -L fm-lab send-keys -t "$TARGET" -l /quit
tmux -L fm-lab send-keys -t "$TARGET" Enter
wait_state dead
assert_output 'Live sibling stays working after the other agent exits' 'state: working' "$(ID=live-sibling read_state)"
tmux -L fm-lab capture-pane -p -t "$TARGET" > "$EVIDENCE/pi-exited-pane.txt"
git show 7da4c3621370534ff9689843d2b77f34158057fb:bin/fm-crew-state.sh > "$BASELINE"
assert_output 'Before the fix: exited Pi with stale idle record and working event' 'state: working' "$(bash "$BASELINE" "$ID")"
assert_output 'After the fix: exited Pi with stale idle record and working event' 'agent gone, pane shell remains' "$(read_state)"
"$ROOT/bin/fm-busy-event.sh" apply "$LAB/state" "$ID" busy --gen "$GEN" --source pi-ext --event user-prompt-submit
assert_output 'Before the fix: exited Pi with stale busy record' 'state: working' "$(bash "$BASELINE" "$ID")"
assert_output 'After the fix: exited Pi with stale busy record' 'agent gone, pane shell remains' "$(read_state)"
for verb in needs-decision blocked paused; do
  write_status "$verb: older nonterminal declaration"
  assert_output "Stopped Pi cannot hide behind $verb" 'agent gone, pane shell remains' "$(read_state)"
done
for kind in scout ship; do
  write_meta "$kind"
  for verb in done failed; do
    write_status "$verb: recorded terminal outcome before exit"
    assert_output "Exited $kind preserves $verb" "state: $verb" "$(read_state)"
  done
done
git -C "$LAB/project" init -q
git -C "$LAB/project" -c user.name=Test -c user.email=test@example.invalid -c commit.gpgsign=false commit -q --allow-empty -m 'Lab initial commit'
write_meta ship direct-PR
write_status 'done: implementation ready'
assert_output 'Stopped ship cannot falsely declare an unpublished commit finished' 'state: blocked' "$(read_state)"
git init --bare -q "$LAB/published.git"
git -C "$LAB/project" remote add origin "$LAB/published.git"
git -C "$LAB/project" push -q origin HEAD:refs/heads/main
assert_output 'Stopped ship preserves done after the commit reaches the disposable remote' 'state: done' "$(read_state)"
write_meta secondmate
write_status 'paused: waiting for the next delegated task'
assert_output 'Secondmate idle-shell handling remains unchanged' 'state: paused' "$(read_state)"
write_meta scout
write_status 'working: active lifecycle record'
tmux -L fm-lab send-keys -t "$TARGET" -l 'sleep 60'
tmux -L fm-lab send-keys -t "$TARGET" Enter
wait_state ambiguous
assert_output 'An unrelated foreground process is not positive evidence of agent death' 'state: working' "$(read_state)"
tmux -L fm-lab send-keys -t "$TARGET" C-c
wait_state dead
tmux -L fm-lab kill-window -t "$TARGET"
assert_output 'A missing endpoint cannot reuse stale working activity' 'backend target gone' "$(read_state)"
printf 'All live tmux scenarios passed.\n'
