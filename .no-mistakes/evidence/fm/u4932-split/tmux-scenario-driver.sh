#!/usr/bin/env bash
set -euo pipefail
RUN_ROOT=$PWD
AREA="$RUN_ROOT/.test-treehouse/tmux-live"
mkdir -p "$AREA/tmp"
export TMPDIR="$AREA/tmp"
. "$RUN_ROOT/tests/git-config-helpers.sh"
unset NO_MISTAKES_GATE FM_GATE_REFUSE_BYPASS FM_ROOT_OVERRIDE FM_STATE_OVERRIDE FM_DATA_OVERRIDE FM_CONFIG_OVERRIDE FM_PROJECTS_OVERRIDE FM_HOME FM_ROOT STATE TMUX TMUX_PANE HERDR_ENV HERDR_SESSION HERDR_SOCKET_PATH HERDR_PANE_ID HERDR_TAB_ID HERDR_WORKSPACE_ID TERM_PROGRAM FM_BACKEND FM_TEST_SEAM
"$RUN_ROOT/bin/fm-lab-home.sh" create "$AREA/home-a"
"$RUN_ROOT/bin/fm-lab-home.sh" create "$AREA/home-b"
SOCKET_DIR=$("$RUN_ROOT/bin/fm-lab-home.sh" tmux-dir "$AREA/home-a")
SOCKET="$SOCKET_DIR/tmux-$(id -u)/fm-lab"
cleanup() {
  if [ -S "$SOCKET" ]; then tmux -S "$SOCKET" kill-server || true; fi
  "$RUN_ROOT/bin/fm-lab-home.sh" teardown "$AREA/home-a"
}
trap cleanup EXIT
export SHELL=/bin/bash
TMUX_TMPDIR="$SOCKET_DIR" tmux -L fm-lab -f /dev/null new-session -d -s primary -n firstmate -c "$RUN_ROOT" '/bin/bash --noprofile --norc'
tmux -S "$SOCKET" set-option -g default-shell /bin/bash
tmux -S "$SOCKET" set-option -g default-command '/bin/bash --noprofile --norc'
export TMUX
TMUX=$(tmux -S "$SOCKET" display-message -p '#{socket_path},#{pid},#{session_id}')
TMUX=${TMUX/\$/}
for side in a b; do
  export FM_HOME="$AREA/home-$side"
  printf 'manual\n' > "$FM_HOME/config/backlog-backend"
  printf 'tmux\n' > "$FM_HOME/config/backend"
  git clone -q "$RUN_ROOT/.test-treehouse/live/origin" "$FM_HOME/projects/project"
  task="pool-live-$side-$$"
  "$RUN_ROOT/bin/fm-brief.sh" "$task" project --scout
  python3 - "$FM_HOME/data/$task/brief.md" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
p.write_text(p.read_text().replace('{TASK}', 'Validate allocation into a home-specific Treehouse pool.').replace('{FIRSTMATE_SPEC}', 'This test only starts the installed Codex version command; do not submit model work.'))
PY
  printf '\nDispatch from home %s through real tmux and real Treehouse, with the installed Codex version command:\n' "$side"
  "$RUN_ROOT/bin/fm-spawn.sh" "$task" "$FM_HOME/projects/project" --scout 'codex --version'
  meta="$FM_HOME/state/$task.meta"
  wt=$(sed -n 's/^worktree=//p' "$meta")
  window=$(sed -n 's/^window=//p' "$meta")
  printf 'Recorded allocated directory: %s\n' "$wt"
  git -C "$wt" rev-parse --git-common-dir
  [ "$(git -C "$wt" rev-parse --git-common-dir)" = "$FM_HOME/projects/project/.git" ]
  expected=$(FM_HOME="$FM_HOME" bash -c '. "$1/bin/fm-wake-lib.sh"; fm_treehouse_home_root "$FM_HOME"' _ "$RUN_ROOT")
  case "$wt" in "$expected/"*) ;; *) exit 1 ;; esac
  tmux -S "$SOCKET" capture-pane -p -t "$window" -S -30
  printf '%s\n' "$wt" > "$AREA/$side.path"
done
[ "$(cat "$AREA/a.path")" != "$(cat "$AREA/b.path")" ]
printf '\nBoth real dispatches allocated from distinct home roots and correct clone ownership.\n'
