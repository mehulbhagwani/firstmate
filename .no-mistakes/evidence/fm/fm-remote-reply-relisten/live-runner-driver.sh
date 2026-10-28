#!/usr/bin/env bash
# Live drive of the real fm-procevent runner + remote reply adapter.
set -u
ROOT=$1
LAB=$(mktemp -d "${TMPDIR:-/tmp}/fm-lab.XXXXXX"); LAB=$(cd "$LAB" && pwd -P)
env -u NO_MISTAKES_GATE "$ROOT/bin/fm-lab-home.sh" create "$LAB" >/dev/null
REMOTE="$LAB/remote-home"; CLAIMS="$LAB/claims"; SRCTMP="$LAB/srctmp"; SHIM="$LAB/shim"
mkdir -p "$REMOTE/state" "$REMOTE/data/reply" "$CLAIMS" "$SRCTMP" "$SHIM"
cleanup() {
  FM_HOME="$LAB" FM_PROCEVENT_CLAIM_ROOT="$CLAIMS" "$ROOT/bin/fm-procevent.sh" sweep-home >/dev/null 2>&1 || true
  [ -f "$LAB/remote-jobs/worker.pid" ] && { . "$ROOT/bin/fm-remote-job-lib.sh"; fm_remote_job_stop_worker_tree "$(cat "$LAB/remote-jobs/worker.pid")" || true; }
  rm -rf -- "$LAB"
}
trap cleanup EXIT
: > "$REMOTE/state/parent-replies.status"
# Transport shim: logs every connection. MODE=realssh execs the real ssh binary;
# MODE=local runs the real remote entrypoint locally (stand-in for sshd only).
cat > "$SHIM/ssh" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FM_LIVE_POLL_LOG"
if [ "$FM_LIVE_MODE" = realssh ]; then /usr/bin/ssh "$@"; rc=$?; printf "remote-leg-exit=%s\n" "$rc" >> "$FM_LIVE_POLL_LOG.rc"; exit "$rc"; fi
while [ "$#" -gt 0 ]; do case "$1" in -o) shift 2;; --) shift; break;; *) break;; esac; done
host=$1; shift 2
case "${FM_LIVE_FORCE:-}" in ''|none) ;; banner) printf 'Welcome to remote-mac\n'; exit 0;; *) exit "$FM_LIVE_FORCE";; esac
"$FM_LIVE_ENTRY" "$@"; rc=$?; printf "remote-leg-exit=%s\n" "$rc" >> "$FM_LIVE_POLL_LOG.rc"; exit "$rc"
SH
chmod +x "$SHIM/ssh"
reg() { printf -- '- ios - iOS delivery (host: %s; root: %s; home: %s; scope: iOS work; projects: alpha; added 2026-08-02)\n' "$1" "$ROOT" "$2" > "$LAB/data/secondmates.md"; }
renv() {
  env -u NO_MISTAKES_GATE -u FM_GATE_REFUSE_BYPASS -u FM_STATE_OVERRIDE -u FM_DATA_OVERRIDE -u FM_CONFIG_OVERRIDE \
  FM_HOME="$LAB" FM_ROOT_OVERRIDE="$ROOT" FM_PROCEVENT_CLAIM_ROOT="$CLAIMS" FM_SSH_BIN="$SHIM/ssh" \
  FM_LIVE_ENTRY="$ROOT/bin/fm-remote-entrypoint.sh" FM_LIVE_POLL_LOG="$LAB/polls" TMPDIR="$SRCTMP" \
  FM_REMOTE_JOB_PLATFORM_OVERRIDE=Linux FM_REMOTE_JOB_STATE_ROOT="$LAB/remote-jobs" \
  FM_REMOTE_REPLY_WAIT_SECONDS="${WAIT:-3}" FM_PROCEVENT_LAUNCH_FLOOR_SECONDS=1 "$@"
}
A="$ROOT/bin/fm-procevent-remote-reply.sh"
owner() { renv "$ROOT/bin/fm-procevent.sh" list 2>/dev/null | awk -v id="$SID" 'NR>1 && $1==id {print $3; exit}'; }
staged() { find "$SRCTMP" -name 'fm-remote-reply-source.*' 2>/dev/null | wc -l | tr -d ' '; }
polls() { [ -f "$LAB/polls" ] && wc -l < "$LAB/polls" | tr -d ' ' || echo 0; }
stopl() { local pid; pid=$(sed -n 2p "$CLAIMS/$SID.claim" 2>/dev/null); [ -n "$pid" ] || return 0
  kill -TERM -- -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null; for _ in $(seq 80); do kill -0 "$pid" 2>/dev/null || return 0; sleep 0.05; done; return 1; }

reg remote-mac "$REMOTE"
SID=$(renv "$A" source-id ios); echo "source id: $SID"
FM_LIVE_MODE=local renv "$A" arm ios

run_relisten() { # label mode force host home
  local label=$1; : > "$LAB/polls"; : > "$LAB/polls.rc"; reg "$4" "$5"
  FM_LIVE_MODE=$2 FM_LIVE_FORCE=$3 renv "$ROOT/bin/fm-procevent.sh" start "$SID" > "$LAB/run.out" 2>&1 &
  local runner=$!
  for _ in $(seq 60); do [ "$(polls)" -ge 3 ] && break; sleep 0.25; done
  local st; st=$(ps -p "$runner" -o stat= 2>/dev/null | tr -d ' ')
  echo "== $label: connections=$(polls) runner_alive=$([ -n "$st" ] && [ "${st#Z}" = "$st" ] && echo yes || echo no) owner=$(owner) staged_files=$(staged) remote_leg_exits=[$(sort "$LAB/polls.rc" | uniq -c | tr -s " \n" " ")]"
  [ "$2" = realssh ] && { echo "   real ssh stderr sample:"; FM_LIVE_MODE=realssh FM_LIVE_POLL_LOG=/dev/null /usr/bin/ssh -o BatchMode=yes "$4" true 2>&1 | head -1 | sed 's/^/     /'; echo "     (exit ${PIPESTATUS[0]})"; }
  stopl; wait "$runner" 2>/dev/null
  echo "   after stop: owner=$(owner) staged_files=$(staged) runner_output=[$(tr '\n' ' ' < "$LAB/run.out")] cursor=$(cat "$LAB/state/remote-replies/ios.cursor" 2>/dev/null | tr '\n' ' ')"
}
run_failed() { # label force
  : > "$LAB/polls"; : > "$LAB/polls.rc"; reg remote-mac "$REMOTE"
  FM_LIVE_MODE=local FM_LIVE_FORCE=$2 renv "$ROOT/bin/fm-procevent.sh" start "$SID" > "$LAB/run.out" 2>&1
  local rc=$?; sleep 2
  echo "== $1: runner exited rc=$rc connections=$(polls) owner=$(owner) staged_files=$(staged) runner_output=[$(tr '\n' ' ' < "$LAB/run.out")]"
}

echo "### Scenario 1: genuine SSH transport failure via the real /usr/bin/ssh (unresolvable host)"
run_relisten ssh255-real realssh none fm-lab-nohost.invalid "$REMOTE"
echo "### Scenario 2: real remote reader exit 1 (remote home has no state/ directory)"
mkdir -p "$LAB/broken-home"
run_relisten reader-exit1-real local none remote-mac "$LAB/broken-home"
echo "### Scenario 3: remote leg exit 2 (forced at transport shim)"
run_relisten exit2 local 2 remote-mac "$REMOTE"
echo "### Scenario 4: other failures stay on failed-read path"
run_failed exit127 127
run_failed exit126 126
run_failed rc0-banner banner
echo "### Scenario 5: normal delivery and staged-file cleanup"
reg remote-mac "$REMOTE"; : > "$LAB/polls"
FM_LIVE_MODE=local FM_LIVE_FORCE=none renv "$ROOT/bin/fm-procevent.sh" start "$SID" > "$LAB/run.out" 2>&1 &
runner=$!
sleep 2
printf 'done [corr=0123456789abcdef] [at=1700000000]: live gate check delivered\n' >> "$REMOTE/state/parent-replies.status"
for _ in $(seq 80); do grep -q 'live gate check delivered' "$LAB/state/ios.status" 2>/dev/null && break; sleep 0.25; done
echo "== delivery: parent mirror line: $(grep 'live gate check' "$LAB/state/ios.status" 2>/dev/null)"
echo "   cursor=$(tr '\n' ' ' < "$LAB/state/remote-replies/ios.cursor") owner=$(owner) staged_after_delivery_and_relisten=$(staged)"
n=0; for _ in $(seq 40); do n=$(staged); [ "$n" -ge 1 ] && break; sleep 0.1; done
echo "   staged files observed while listener blocked in a wait window: $n (1 = the in-flight read)"
renv "$ROOT/bin/fm-procevent.sh" sweep-home > "$LAB/sweep.out" 2>&1; wait "$runner" 2>/dev/null
sleep 1
echo "   after sweep-home shutdown: owner=$(owner) staged_files=$(staged) sweep=[$(tr '\n' ' ' < "$LAB/sweep.out")]"
echo "### Scenario 6: listener shutdown (process-group TERM, as fm-procevent stop does) while blocked in remote read"
renv "$A" register ios >/dev/null 2>&1 || true
set -m; FM_LIVE_MODE=local FM_LIVE_FORCE=none WAIT=20 renv "$A" source ios > /dev/null 2>&1 & src=$!; set +m
n=0; for _ in $(seq 40); do n=$(staged); [ "$n" -ge 1 ] && break; sleep 0.1; done
echo "   staged while blocked: $n"; kill -TERM -- -"$src"; wait "$src"; rc=$?; sleep 0.5; echo "   source exit=$rc staged after group TERM: $(staged)"
echo "### Scenario 6b: TERM to only the top adapter pid (edge case)"
FM_LIVE_MODE=local FM_LIVE_FORCE=none WAIT=8 renv "$A" source ios > /dev/null 2>&1 & src=$!
n=0; for _ in $(seq 40); do n=$(staged); [ "$n" -ge 1 ] && break; sleep 0.1; done
kill -TERM "$src"; wait "$src"; rc=$?; echo "   source exit=$rc staged right after: $(staged)"; sleep 10; echo "   staged after the 8s remote wait window ends: $(staged)"
