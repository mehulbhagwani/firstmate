#!/bin/bash
set -eu
ROOT=$PWD
LAB=$(mktemp -d "$PWD/.identity-live.XXXXXX")
WORKER="$LAB/root/bin/fm-remote-job-worker.sh"
fixture_pids() { ps -eo pid=,command= | awk -v w="$WORKER" 'index($0,w) {print $1}'; }
cleanup() { for p in $(fixture_pids); do kill -KILL "$p" 2>/dev/null || true; done; rm -rf "$LAB"; }
trap cleanup EXIT
mkdir -p "$LAB/root/bin" "$LAB/account"
cp bin/fm-remote-job-lib.sh bin/fm-remote-job-worker.sh "$LAB/root/bin/"
printf 'fixture\n' > "$LAB/root/AGENTS.md"
export FM_REMOTE_JOB_STATE_ROOT="$LAB/state" FM_REMOTE_JOB_PLATFORM_OVERRIDE=Linux
. "$ROOT/bin/fm-remote-job-lib.sh"
fm_remote_job_ensure_worker "$LAB/root" "$LAB/account"
LOCK="$LAB/state/worker.lock"
old=$(cat "$LOCK/pid")
legacy=$(LC_ALL=C /bin/ps -p "$old" -o lstart=)
printf '%s\n' "$legacy" > "$LOCK/start"
LC_ALL=de_DE.UTF-8 fm_remote_job_worker_owned_alive "$LAB/root" "$LAB/account"
printf 'Legacy C cookie accepted under German locale for live worker %s\n' "$old"
printf 'obsolete-code\n' > "$LAB/state/worker.identity"
fm_remote_job_ensure_worker "$LAB/root" "$LAB/account"
new=$(cat "$LOCK/pid")
[ "$old" != "$new" ]
! kill -0 "$old" 2>/dev/null
printf 'Upgrade replaced old worker %s with %s; old process exited\n' "$old" "$new"
for i in 1 2 3 4 5; do
 fm_remote_job_ensure_worker "$LAB/root" "$LAB/account"
 [ "$(cat "$LOCK/pid")" = "$new" ]
 count=$(ps -eo command= | awk -v w="$WORKER" 'substr($0,length($0)-length(w)+1)==w {n++} END {print n+0}')
 [ "$count" = 2 ]
 printf 'Ensure %s: same worker %s, %s worker-command processes (supervisor and heartbeat)\n' "$i" "$new" "$count"
done
