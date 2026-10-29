#!/usr/bin/env bash
# Manual drive of `fm-procevent-remote-reply.sh source` against a disposable
# parent/remote home and a fake ssh transport. Usage: drive-source.sh <repo-root>
set -u
ROOT=$1
T=$(mktemp -d "${TMPDIR:-/tmp}/fm-drive.XXXXXX"); T=$(cd "$T" && pwd -P)
P=$T/parent R=$T/remote ST=$T/stage
mkdir -p "$P/data" "$P/state" "$R/state" "$R/data/reply" "$T/claims" "$ST" "$T/bin"
echo "- ios - iOS delivery (host: remote-mac; root: $ROOT; home: $R; scope: iOS; projects: alpha; added 2026-08-02)" > "$P/data/secondmates.md"
: > "$R/state/parent-replies.status"
cat > "$T/bin/ssh" <<'SH'
#!/usr/bin/env bash
while [ "$#" -gt 0 ]; do case "$1" in -o) shift 2;; --) shift; break;; *) exit 90;; esac; done
[ -n "${FAKE_RC:-}" ] && { printf 'ssh: connect to host remote-mac port 22: Connection refused\n'; exit "$FAKE_RC"; }
shift 2; exec "$ROOT_ENTRY" "$@"
SH
chmod +x "$T/bin/ssh"
run() { FM_HOME="$P" FM_ROOT_OVERRIDE="$ROOT" FM_PROCEVENT_CLAIM_ROOT="$T/claims" FM_SSH_BIN="$T/bin/ssh" \
  ROOT_ENTRY="$ROOT/bin/fm-remote-entrypoint.sh" FM_REMOTE_JOB_PLATFORM_OVERRIDE=Linux \
  FM_REMOTE_JOB_STATE_ROOT="$T/jobs" FM_REMOTE_REPLY_WAIT_SECONDS=1 TMPDIR="$ST" "$@"; }
A="$ROOT/bin/fm-procevent-remote-reply.sh"
run "$A" arm ios
for rc in 255 1 2 3 127; do
  FAKE_RC=$rc run "$A" source ios > "$T/out" 2>"$T/err"; got=$?
  printf 'remote leg exit %-3s -> source exit %-3s stdout_bytes=%s staged_left=%s\n' \
    "$rc" "$got" "$(wc -c < "$T/out" | tr -d ' ')" "$(ls "$ST" | wc -l | tr -d ' ')"
done
printf 'hello-from-remote\n' >> "$R/state/parent-replies.status"
run "$A" source ios > "$T/out" 2>"$T/err"; got=$?
printf 'healthy delta leg     -> source exit %-3s staged_left=%s first_lines:\n' "$got" "$(ls "$ST" | wc -l | tr -d ' ')"
head -c 400 "$T/out"; echo
if [ -f "$T/jobs/worker.pid" ]; then . "$ROOT/bin/fm-remote-job-lib.sh"; fm_remote_job_stop_worker_tree "$(cat "$T/jobs/worker.pid")" || true; fi
rm -rf "$T"
