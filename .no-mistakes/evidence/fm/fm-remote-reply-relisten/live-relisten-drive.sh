#!/usr/bin/env bash
# Live drive: one real fm-procevent.sh runner holding a remote-reply claim
# survives a real SSH transport failure (real /usr/bin/ssh to a closed port,
# exit 255), a real remote reader exit 1 (remote state/ missing), and a real
# remote reader exit 2 (reader usage error, help text on stdout), then
# delivers a reply once the remote recovers - same pid, claim held throughout.
set -u
ROOT=${1:?worktree}
LAB=$(mktemp -d "${TMPDIR:-/tmp}/fm-lab-relisten.XXXXXX"); LAB=$(cd "$LAB" && pwd -P)
PARENT=$LAB/parent REMOTE=$LAB/remote CLAIMS=$LAB/claims BIN=$LAB/bin
mkdir -p "$PARENT/data" "$PARENT/state" "$REMOTE/state" "$REMOTE/data/reply" "$CLAIMS" "$BIN"
printf '%s\n' "- ios - iOS delivery (host: remote-mac; root: $ROOT; home: $REMOTE; scope: iOS work; projects: alpha; added 2026-08-02)" > "$PARENT/data/secondmates.md"
printf '# Report\n\nGreen after outage.\n' > "$REMOTE/data/reply/report.md"
: > "$REMOTE/state/parent-replies.status"
MODE=$LAB/mode; echo healthy > "$MODE"; POLLS=$LAB/polls; : > "$POLLS"
# ssh transport: in ssh255 mode run the REAL ssh against a closed local port;
# otherwise act as the remote host and run the real remote entrypoint locally.
cat > "$BIN/ssh" <<SH
#!/usr/bin/env bash
mode=\$(cat "$MODE"); printf '%s %s\n' "\$(date +%T)" "\$mode" >> "$POLLS"
if [ "\$mode" = ssh255 ]; then
  /usr/bin/ssh -F /dev/null -o BatchMode=yes -o ConnectTimeout=2 -p 1 127.0.0.1 true; rc=\$?
  printf '%s   -> ssh rc=%s\n' "\$(date +%T)" "\$rc" >> "$POLLS"; exit \$rc
fi
while [ "\$#" -gt 0 ]; do case "\$1" in -o) shift 2 ;; --) shift; break ;; *) exit 90 ;; esac; done
shift 2
if [ "\$mode" = exit2 ]; then
  # Real reader, malformed invocation -> its own usage() exit 2 (text on stdout).
  env FM_HOME="$REMOTE" bash "$ROOT/bin/fm-remote-delta-read.sh" only-one-arg; rc=\$?
  printf '%s   -> remote reader rc=%s\n' "\$(date +%T)" "\$rc" >> "$POLLS"; exit \$rc
fi
"$ROOT/bin/fm-remote-entrypoint.sh" "\$@"; rc=\$?
printf '%s   -> remote leg rc=%s\n' "\$(date +%T)" "\$rc" >> "$POLLS"; exit \$rc
SH
chmod +x "$BIN/ssh"
renv() {
  env -u FM_ROOT_OVERRIDE -u FM_STATE_OVERRIDE -u FM_DATA_OVERRIDE -u FM_CONFIG_OVERRIDE \
    FM_HOME="$PARENT" FM_PROCEVENT_CLAIM_ROOT="$CLAIMS" FM_SSH_BIN="$BIN/ssh" \
    FM_REMOTE_JOB_PLATFORM_OVERRIDE=Linux FM_REMOTE_JOB_STATE_ROOT="$LAB/remote-jobs" \
    FM_REMOTE_REPLY_WAIT_SECONDS=3 FM_PROCEVENT_LAUNCH_FLOOR_SECONDS=1 "$@"
}
A="$ROOT/bin/fm-procevent-remote-reply.sh"
SID=$(renv "$A" source-id ios); echo "source: $SID"
renv "$A" arm ios
owner() { renv "$ROOT/bin/fm-procevent.sh" list 2>/dev/null | awk -v id="$SID" 'NR>1 && $1==id {print $3; exit}'; }
claimpid() { sed -n 2p "$CLAIMS/$SID.claim" 2>/dev/null; }
echo ssh255 > "$MODE"
renv "$ROOT/bin/fm-procevent.sh" start "$SID" > "$LAB/runner.out" 2>&1 &
RUNNER=$!
sleep 1
PID0=$(claimpid); echo "runner pid=$RUNNER claim pid=$PID0"
ok=1
phase() { # <mode> <seconds>
  local m=$1 s=$2 before after
  [ "$m" = exit1 ] && mv "$REMOTE/state" "$REMOTE/state.away"
  echo "$m" > "$MODE"; before=$(grep -c " $m\$" "$POLLS")
  sleep "$s"
  after=$(grep -c " $m\$" "$POLLS")
  [ "$m" = exit1 ] && mv "$REMOTE/state.away" "$REMOTE/state"
  printf '%-7s polls=%s owner=%s claim_pid=%s runner_alive=%s inbox_results=%s\n' "$m" "$((after-before))" \
    "$(owner)" "$(claimpid)" "$(kill -0 $RUNNER 2>/dev/null && echo yes || echo no)" \
    "$(find "$PARENT/state/procevent-inbox" -name '*.result' 2>/dev/null | wc -l | tr -d ' ')"
  [ "$((after-before))" -ge 2 ] && [ "$(owner)" = live ] && [ "$(claimpid)" = "$PID0" ] || ok=0
}
# Reader-exit evidence straight from the real reader (outside the runner):
printf 'direct real reader, missing state/: '; FM_HOME="$LAB/nohome" bash "$ROOT/bin/fm-remote-delta-read.sh" state/parent-replies.status 0 x 1 >/dev/null 2>&1; echo "exit $?"
printf "direct real reader, bad args: "; FM_HOME="$REMOTE" bash "$ROOT/bin/fm-remote-delta-read.sh" a >/dev/null 2>&1; echo "exit $?"
printf 'direct real ssh, closed port: '; /usr/bin/ssh -F /dev/null -o BatchMode=yes -o ConnectTimeout=2 -p 1 127.0.0.1 true >/dev/null 2>&1; echo "exit $?"
phase ssh255 10
phase exit1 10
phase exit2 10
echo healthy > "$MODE"; sleep 1
printf 'done [corr=fedcba9876543210] [at=1700000000]: recovered report=data/reply/report.md\n' >> "$REMOTE/state/parent-replies.status"
for _ in $(seq 1 200); do grep -q 'corr=fedcba9876543210' "$PARENT/state/ios.status" 2>/dev/null && break; sleep 0.1; done
echo "--- parent state/ios.status after recovery:"; cat "$PARENT/state/ios.status" 2>/dev/null || { echo MISSING; ok=0; }
grep -q 'corr=fedcba9876543210' "$PARENT/state/ios.status" 2>/dev/null || ok=0
grep -qiE 'WSAE|usage|error|Connection refused' "$PARENT/state/ios.status" 2>/dev/null && { echo "diagnostics leaked into parent stream"; ok=0; }
printf 'after delivery: owner=%s claim_pid=%s (initial %s)\n' "$(owner)" "$(claimpid)" "$PID0"
[ "$(owner)" = live ] && [ "$(claimpid)" = "$PID0" ] || ok=0
echo "--- runner output:"; cat "$LAB/runner.out"
echo "--- poll log (time mode per SSH launch):"; cat "$POLLS"
kill -TERM -- -"$PID0" 2>/dev/null || kill -TERM "$PID0" 2>/dev/null
wait "$RUNNER" 2>/dev/null
renv "$ROOT/bin/fm-procevent.sh" sweep-home >/dev/null 2>&1
rm -rf -- "$LAB"
[ "$ok" = 1 ] && echo "LIVE RESULT: PASS" || echo "LIVE RESULT: FAIL"
