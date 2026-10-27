#!/usr/bin/env bash
# Disposable live lab: real fm-procevent runner + real fm-on.sh + real /usr/bin/ssh
# against an unreachable host, then recovery over a local transport.
set -u
ROOT=$1
LAB=$(mktemp -d "${TMPDIR:-/tmp}/fm-lab.XXXXXX"); LAB=$(cd "$LAB" && pwd -P)
PARENT=$LAB/parent; REMOTE=$LAB/remote; CLAIMS=$LAB/claims
mkdir -p "$PARENT/data" "$PARENT/state" "$REMOTE/state" "$REMOTE/data/reply" "$CLAIMS" "$LAB/tmp"
cat > "$PARENT/data/secondmates.md" <<EOF
- ios - iOS delivery (host: fm-lab-dead; root: $ROOT; home: $REMOTE; scope: iOS work; projects: alpha; added 2026-10-27)
EOF
: > "$REMOTE/state/parent-replies.status"
printf 'Host fm-lab-dead\n  HostName 127.0.0.1\n  Port 1\n  ConnectTimeout 2\n  BatchMode yes\n' > "$LAB/ssh_config"
echo dead > "$LAB/mode"
cat > "$LAB/ssh-wrapper" <<SH
#!/usr/bin/env bash
printf '%s %s\n' "\$(date +%T)" "\$(cat $LAB/mode)" >> $LAB/ssh-calls.log
case "\$(cat $LAB/mode)" in
  dead) exec /usr/bin/ssh -F $LAB/ssh_config "\$@" ;;
  wsl) printf 'A\000 connection attempt failed because the connected party did not properly respond\000 Error code: Bash/Service/WSAETIMEDOUT\000\n'; exit 255 ;;
  up) while [ "\$#" -gt 0 ]; do case "\$1" in -o) shift 2;; --) shift; break;; *) shift;; esac; done
      shift 2; exec "$ROOT/bin/fm-remote-entrypoint.sh" "\$@" ;;
esac
SH
chmod +x "$LAB/ssh-wrapper"
renv() {
  env -u NO_MISTAKES_GATE -u FM_STATE_OVERRIDE -u FM_DATA_OVERRIDE -u FM_CONFIG_OVERRIDE -u FM_PROJECTS_OVERRIDE \
  FM_HOME="$PARENT" FM_ROOT_OVERRIDE="$ROOT" FM_PROCEVENT_CLAIM_ROOT="$CLAIMS" \
  FM_SSH_BIN="$LAB/ssh-wrapper" FM_REMOTE_JOB_PLATFORM_OVERRIDE=Linux \
  FM_REMOTE_JOB_STATE_ROOT="$LAB/remote-jobs" FM_REMOTE_REPLY_WAIT_SECONDS=4 \
  FM_PROCEVENT_LAUNCH_FLOOR_SECONDS=1 TMPDIR="$LAB/tmp" "$@"
}
A=$ROOT/bin/fm-procevent-remote-reply.sh
echo "== real ssh to unreachable host (direct fm-on probe) =="
renv "$ROOT/bin/fm-on.sh" ios fm-remote-delta-read.sh state/parent-replies.status 0 x 1 >/dev/null; echo "fm-on.sh exit=$?"
echo "== arm =="
renv "$A" arm ios
SID=$(renv "$A" source-id ios)
echo "== one source leg with real ssh exit 255 =="
renv "$A" source ios > "$LAB/leg.out"; echo "source exit=$? stdout_bytes=$(wc -c < "$LAB/leg.out" | tr -d ' ')"
echo "== start runner; transport dead =="
renv "$ROOT/bin/fm-procevent.sh" start "$SID" > "$LAB/runner.out" 2>&1 &
RUNNER=$!
sleep 12
echo "ssh legs while dead: $(grep -c dead "$LAB/ssh-calls.log")"
echo "runner alive: $(kill -0 $RUNNER 2>/dev/null && echo yes || echo no)"
renv "$ROOT/bin/fm-procevent.sh" list
echo "== switch to Windows WSL-shaped diagnostic transport =="
echo wsl > "$LAB/mode"; sleep 10
echo "ssh legs with WSL diagnostic: $(grep -c wsl "$LAB/ssh-calls.log")"
echo "runner alive: $(kill -0 $RUNNER 2>/dev/null && echo yes || echo no)"
echo "captured results so far: $(find "$PARENT/state/procevent-inbox" -name '*.result' 2>/dev/null | wc -l | tr -d ' ')"
echo "cursor files: $(ls "$PARENT/state"/*.cursor "$PARENT"/state/*/*.cursor 2>/dev/null | xargs -I{} sh -c 'echo {}; cat {}')"
echo "parent ios.status: $(cat "$PARENT/state/ios.status" 2>/dev/null || echo '<absent>')"
echo "leftover staged files: $(ls "$LAB/tmp" | grep -c fm-remote-reply-source || true)"
echo "== transport recovers; remote mate writes a reply =="
echo up > "$LAB/mode"
printf 'done [corr=0123456789abcdef] [at=1700000000]: build verified after link drop\n' >> "$REMOTE/state/parent-replies.status"
for _ in $(seq 1 120); do grep -q 'after link drop' "$PARENT/state/ios.status" 2>/dev/null && break; sleep 0.25; done
echo "parent ios.status: $(cat "$PARENT/state/ios.status" 2>/dev/null || echo '<absent>')"
echo "runner alive (same pid $RUNNER): $(kill -0 $RUNNER 2>/dev/null && echo yes || echo no)"
echo "captured results: $(find "$PARENT/state/procevent-inbox" -name '*.result' | sed "s|$LAB/||")"
find "$PARENT/state" -name '*.cursor' -exec sh -c 'echo "cursor {}:"; cat {}' \; | sed "s|$LAB/||"
renv "$ROOT/bin/fm-procevent.sh" list
echo "== stop listener (TERM process group) =="
pid=$(sed -n 2p "$CLAIMS/$SID.claim"); kill -TERM -- -"$pid" 2>/dev/null; sleep 2
echo "leftover staged files after stop: $(ls "$LAB/tmp" | grep -c fm-remote-reply-source || true)"
renv "$ROOT/bin/fm-procevent.sh" sweep-home >/dev/null 2>&1
[ -f "$LAB/remote-jobs/worker.pid" ] && kill -TERM -- -"$(cat "$LAB/remote-jobs/worker.pid")" 2>/dev/null; pkill -f "$LAB" 2>/dev/null
echo "== runner log tail =="; tail -5 "$LAB/runner.out"
rm -rf "$LAB"; echo "lab removed"
