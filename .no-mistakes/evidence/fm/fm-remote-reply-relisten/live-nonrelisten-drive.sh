#!/usr/bin/env bash
# Adversarial live drive: statuses outside 255/1/2 (remote reader missing ->
# 127) and an rc=0 non-schema banner must still end the runner as failed reads,
# not relisten forever. Real fm-procevent.sh runner, disposable lab.
set -u
ROOT=${1:?worktree}
for mode in exit127 banner; do
LAB=$(mktemp -d "${TMPDIR:-/tmp}/fm-lab-norelisten.XXXXXX"); LAB=$(cd "$LAB" && pwd -P)
PARENT=$LAB/parent REMOTE=$LAB/remote CLAIMS=$LAB/claims BIN=$LAB/bin
mkdir -p "$PARENT/data" "$PARENT/state" "$REMOTE/state" "$CLAIMS" "$BIN"
printf '%s\n' "- ios - iOS delivery (host: remote-mac; root: $ROOT; home: $REMOTE; scope: iOS work; projects: alpha; added 2026-08-02)" > "$PARENT/data/secondmates.md"
: > "$REMOTE/state/parent-replies.status"
cat > "$BIN/ssh" <<SH
#!/usr/bin/env bash
printf 'launch\n' >> "$LAB/polls"
if [ "$mode" = exit127 ]; then
  # Remote checkout lacks the reader: a real bash command-not-found (127).
  bash -c 'fm-remote-delta-read-missing.sh'; exit \$?
fi
printf 'Welcome to remote-mac\n'; exit 0
SH
chmod +x "$BIN/ssh"
renv() { env -u FM_ROOT_OVERRIDE -u FM_STATE_OVERRIDE -u FM_DATA_OVERRIDE -u FM_CONFIG_OVERRIDE \
  FM_HOME="$PARENT" FM_PROCEVENT_CLAIM_ROOT="$CLAIMS" FM_SSH_BIN="$BIN/ssh" \
  FM_REMOTE_REPLY_WAIT_SECONDS=3 FM_PROCEVENT_LAUNCH_FLOOR_SECONDS=1 "$@"; }
SID=$(renv "$ROOT/bin/fm-procevent-remote-reply.sh" source-id ios)
renv "$ROOT/bin/fm-procevent-remote-reply.sh" arm ios >/dev/null
renv "$ROOT/bin/fm-procevent.sh" start "$SID" > "$LAB/runner.out" 2>&1 &
R=$!; sleep 6
printf '%s: launches_in_6s=%s runner_alive=%s owner=%s inbox_results=%s\n' "$mode" \
  "$(wc -l < "$LAB/polls" | tr -d ' ')" "$(kill -0 $R 2>/dev/null && echo yes || echo no)" \
  "$(renv "$ROOT/bin/fm-procevent.sh" list 2>/dev/null | awk -v id="$SID" 'NR>1 && $1==id {print $3; exit}')" \
  "$(find "$PARENT/state/procevent-inbox" -name '*.result' 2>/dev/null | wc -l | tr -d ' ')"
echo "  runner output: $(tr '\n' ' ' < "$LAB/runner.out")"
kill $R 2>/dev/null; wait $R 2>/dev/null
renv "$ROOT/bin/fm-procevent.sh" sweep-home >/dev/null 2>&1; rm -rf -- "$LAB"
done
