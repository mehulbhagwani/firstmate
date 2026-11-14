#!/usr/bin/env bash
set -eu
ROOT=$PWD
EVIDENCE=/Users/mehul/.no-mistakes/evidence/01M7CXKTXMK8MCQX73PEE3SJS5
LAB="$ROOT/.v"
[ ! -e "$LAB" ] || { echo 'Refusing to reuse lab'; exit 1; }
unset FM_GATE_REFUSE_BYPASS FM_ROOT_OVERRIDE FM_STATE_OVERRIDE FM_DATA_OVERRIDE FM_CONFIG_OVERRIDE FM_PROJECTS_OVERRIDE FM_BACKEND HERDR_PANE_ID HERDR_SOCKET_PATH HERDR_SESSION HERDR_WORKSPACE_ID HERDR_TAB_ID
bash bin/fm-lab-home.sh create "$LAB" >/dev/null
mkdir -p "$LAB/tmux" "$LAB/pi"
export TMUX_TMPDIR="$LAB/tmux" FM_HOME="$LAB"
SOCKET="$LAB/tmux/tmux-$(id -u)/fm-lab"
cleanup() {
  rc=$?
  if [ -S "$SOCKET" ]; then command tmux -S "$SOCKET" kill-server || true; fi
  rm -rf "$LAB"
  exit "$rc"
}
trap cleanup EXIT
command tmux -L fm-lab -f /dev/null new-session -d -s primary -n fm-probe -x 120 -y 30 -c "$ROOT" -e FM_HOME="$LAB" /bin/bash --noprofile --norc
export TMUX="$SOCKET,0,0"
TARGET=primary:fm-probe
command tmux -S "$SOCKET" send-keys -t "$TARGET" -l "env PI_CODING_AGENT_DIR='$LAB/pi' pi --offline --no-session --no-context-files --no-extensions --no-mcp --no-skills --no-prompt-templates --no-themes --no-approve --no-tools --tui-mode regular"
command tmux -S "$SOCKET" send-keys -t "$TARGET" Enter
. bin/fm-backend.sh
fm_backend_source tmux
for ((i=0;i<40;i++)); do
  current=$(fm_backend_composer_state tmux "$TARGET")
  [ "$current" != empty ] || break
  sleep 0.5
done
printf 'Installed Pi: %s\n' "$(pi --version)"
printf 'Idle composer: %s\n' "$current"
printf 'Running agent: %s\n' "$(fm_backend_agent_state tmux "$TARGET")"
command tmux -S "$SOCKET" capture-pane -p -t "$TARGET" > "$EVIDENCE/pi-idle.txt"
[ "$current" = empty ]
export FM_COMPOSER_PI_EXECUTABLE=pi
if fm_composer_pi_adapter_installed_pinned; then pinned=yes; else pinned=no; fi
printf 'Installed Pi accepted for banner exception: %s\n' "$pinned"
[ "$pinned" = no ]
cat > "$LAB/state/probe.meta" <<META
window=$TARGET
endpoint_task_id=probe
worktree=$ROOT
project=$ROOT
harness=pi
kind=ship
mode=no-mistakes
yolo=off
model=default
effort=default
META
command tmux -S "$SOCKET" send-keys -t "$TARGET" -l 'preserve this unsent draft'
sleep 0.5
printf 'Draft composer: %s\n' "$(fm_backend_composer_state tmux "$TARGET")"
command tmux -S "$SOCKET" capture-pane -p -t "$TARGET" > "$EVIDENCE/pi-draft-before.txt"
set +e
bash bin/fm-control.sh probe exit > "$EVIDENCE/pi-draft-refusal.txt" 2>&1
rc=$?
set -e
printf 'Exit with unsent draft returned: %s\n' "$rc"
cat "$EVIDENCE/pi-draft-refusal.txt"
[ "$rc" -ne 0 ]
command tmux -S "$SOCKET" capture-pane -p -t "$TARGET" > "$EVIDENCE/pi-draft-after.txt"
grep -Fq 'preserve this unsent draft' "$EVIDENCE/pi-draft-after.txt"
if grep -Fq '/quit' "$EVIDENCE/pi-draft-after.txt"; then echo 'Unexpected exit command in draft'; exit 1; fi
printf 'Unsent draft remains intact; no /quit appended.\n'
command tmux -S "$SOCKET" send-keys -t "$TARGET" C-u
sleep 0.5
printf 'Cleared composer: %s\n' "$(fm_backend_composer_state tmux "$TARGET")"
bash bin/fm-control.sh probe exit > "$EVIDENCE/pi-idle-exit.txt" 2>&1
cat "$EVIDENCE/pi-idle-exit.txt"
printf 'Agent after exit: %s\n' "$(fm_backend_agent_state tmux "$TARGET")"
command tmux -S "$SOCKET" display-message -p -t "$TARGET" 'Preserved terminal: #{session_name}:#{window_name} #{pane_current_command}'
command tmux -S "$SOCKET" capture-pane -p -t "$TARGET" > "$EVIDENCE/pi-after-exit.txt"
[ "$(fm_backend_agent_state tmux "$TARGET")" = dead ]
printf 'Live checks complete.\n'
