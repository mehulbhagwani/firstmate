#!/usr/bin/env bash
set -eu
ROOT=$PWD
EVIDENCE=/Users/mehul/.no-mistakes/evidence/01M7B1FCXHMPTN52EQE2EVH9ZJ
unset FM_GATE_REFUSE_BYPASS FM_ROOT_OVERRIDE FM_STATE_OVERRIDE FM_DATA_OVERRIDE FM_CONFIG_OVERRIDE FM_PROJECTS_OVERRIDE FM_BACKEND HERDR_ENV HERDR_SOCKET_PATH HERDR_SESSION HERDR_PANE_ID HERDR_TAB_ID HERDR_WORKSPACE_ID
LAB=$(mktemp -d "$ROOT/.nm-pi-lab.XXXXXX")
SOCKET_DIR=
cleanup() {
  if [ -n "$SOCKET_DIR" ]; then
    TMUX_TMPDIR="$SOCKET_DIR" command tmux -L fm-lab kill-server 2>/dev/null || true
    "$ROOT/bin/fm-lab-home.sh" teardown "$LAB"
  fi
  rm -rf "$LAB"
}
trap cleanup EXIT
"$ROOT/bin/fm-lab-home.sh" create "$LAB" >/dev/null
SOCKET_DIR=$("$ROOT/bin/fm-lab-home.sh" tmux-dir "$LAB")
export TMUX_TMPDIR=$SOCKET_DIR FM_HOME=$LAB FM_COMPOSER_PI_EXECUTABLE=pi
mkdir -p "$LAB/pi"
command tmux -L fm-lab new-session -d -s primary -n fm-banner -x 120 -y 28 -c "$ROOT" \
  "env PI_CODING_AGENT_DIR='$LAB/pi' pi --offline --no-approve --no-session --no-context-files --no-extensions --no-skills --no-mcp --no-tools --no-prompt-templates --no-themes --tui-mode regular; exec /bin/sh"
SOCKET=$(command tmux -L fm-lab display-message -p -t primary '#{socket_path}')
SERVER_PID=$(command tmux -L fm-lab display-message -p -t primary '#{pid}')
export TMUX="$SOCKET,$SERVER_PID,0"
tmux() { command tmux -S "$SOCKET" "$@"; }
. "$ROOT/bin/fm-tmux-lib.sh"
. "$ROOT/bin/fm-composer-lib.sh"
printf 'Installed Pi: %s\n' "$(pi --version)"
printf 'Configured pins: %s\n' "$FM_COMPOSER_PI_BANNER_PINNED_VERSIONS"
if fm_composer_pi_adapter_installed_pinned; then
  printf 'ERROR: unexpected verified version\n'; exit 1
else
  printf 'Installed-version adapter result: refused (exit status 1)\n'
fi
for ((n=0;n<30;n++)); do
  verdict=$(fm_tmux_composer_state primary:fm-banner)
  [ "$verdict" = empty ] && break
  sleep 1
done
printf 'Live idle composer: %s\n' "$verdict"
tmux capture-pane -e -p -t primary:fm-banner > "$EVIDENCE/pi-idle.ansi"
[ "$verdict" = empty ]
cat > "$LAB/state/banner.meta" <<EOF
window=primary:fm-banner
harness=pi
kind=scout
worktree=$ROOT
project=$ROOT
endpoint_task_id=banner
EOF
printf 'working: disposable verification worker\n' > "$LAB/state/banner.status"
tmux send-keys -t primary:fm-banner -l 'UNSUBMITTED verification input'
sleep 1
verdict=$(fm_tmux_composer_state primary:fm-banner)
printf 'Live composer with typed input: %s\n' "$verdict"
[ "$verdict" = pending ]
tmux capture-pane -e -p -t primary:fm-banner > "$EVIDENCE/pi-pending-before.ansi"
set +e
"$ROOT/bin/fm-control.sh" banner exit > "$EVIDENCE/pi-pending-exit.txt" 2>&1
rc=$?
set -e
cat "$EVIDENCE/pi-pending-exit.txt"
printf 'Exit with unsubmitted input: status=%s\n' "$rc"
[ "$rc" -ne 0 ]
grep -F "composer visibly holds pending text" "$EVIDENCE/pi-pending-exit.txt"
tmux capture-pane -e -p -t primary:fm-banner > "$EVIDENCE/pi-pending-after.ansi"
[ "$(fm_tmux_composer_state primary:fm-banner)" = pending ]
tmux capture-pane -p -t primary:fm-banner | grep -F 'UNSUBMITTED verification input'
printf 'Unsubmitted input preserved.\n'
tmux send-keys -t primary:fm-banner C-u
sleep 1
[ "$(fm_tmux_composer_state primary:fm-banner)" = empty ]
mkdir -p "$LAB/incomplete"
cp -R "$ROOT/bin" "$LAB/incomplete/bin"
for condition in missing unreadable; do
  if [ "$condition" = missing ]; then
    rm "$LAB/incomplete/bin/fm-composer-pi-adapter.sh"
  else
    cp "$ROOT/bin/fm-composer-pi-adapter.sh" "$LAB/incomplete/bin/fm-composer-pi-adapter.sh"
    chmod 000 "$LAB/incomplete/bin/fm-composer-pi-adapter.sh"
  fi
  set +e
  "$LAB/incomplete/bin/fm-control.sh" banner exit > "$EVIDENCE/pi-$condition-adapter-exit.txt" 2>&1
  dep_rc=$?
  set -e
  cat "$EVIDENCE/pi-$condition-adapter-exit.txt"
  printf 'Exit with %s adapter: status=%s; foreground=%s\n' "$condition" "$dep_rc" "$(tmux display-message -p -t primary:fm-banner '#{pane_current_command}')"
  [ "$dep_rc" -ne 0 ]
  [ "$(fm_tmux_composer_state primary:fm-banner)" = empty ]
done
chmod 600 "$LAB/incomplete/bin/fm-composer-pi-adapter.sh"
"$ROOT/bin/fm-control.sh" banner exit > "$EVIDENCE/pi-idle-exit.txt" 2>&1
cat "$EVIDENCE/pi-idle-exit.txt"
tmux capture-pane -e -p -t primary:fm-banner > "$EVIDENCE/pi-after-exit.ansi"
printf 'After exit foreground process: %s\n' "$(tmux display-message -p -t primary:fm-banner '#{pane_current_command}')"
[ -f "$LAB/state/banner.meta" ]
printf 'Exit preserved task record and disposable working directory.\n'
