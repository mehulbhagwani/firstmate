#!/usr/bin/env bash
set -eu
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/fm-user-stop-inbox.XXXXXX")
trap 'rm -rf "$TMP"' EXIT
state="$TMP/state"; task=worthless-author-positioning; inbox="$state/$task.inbox"
mkdir -p "$state" "$inbox"
FM_HOME="$TMP" FM_STATE_OVERRIDE="$state" FM_CONFIG_OVERRIDE="$TMP/config"
export FM_HOME FM_STATE_OVERRIDE FM_CONFIG_OVERRIDE
. "$ROOT/bin/fm-task-inbox-lib.sh"
meta="$state/$task.meta"
cat > "$meta" <<'EOF'
spawn_gen=s1
window=default:wG6:p2
EOF
printf 'schema=fm-task-inbox.v1\nat=2026-10-27T00:00:00Z\n--\nold verification\n' > "$inbox/014.msg"
touch -t 200001010000 "$inbox/014.msg"
fm_task_inbox_mark_user_stop "$state" "$task" s1 default:wG6:p2
[ "$(fm_task_inbox_due_action "$state" "$task")" = quiet ] || { echo 'explicit stop did not suppress old inbox'; exit 1; }
[ -f "$inbox/014.msg" ] || { echo 'explicit stop deleted unread record'; exit 1; }
cat > "$meta" <<'EOF'
spawn_gen=s2
window=default:wG6:p2
EOF
case "$(fm_task_inbox_due_action "$state" "$task")" in
  ring\ *) ;;
  *) echo 'new generation inherited user-stop suppression'; exit 1;;
esac
rm -f "$(fm_task_inbox_user_stop_path "$state" "$task")"
mkdir "$(fm_task_inbox_user_stop_path "$state" "$task")"
if fm_task_inbox_mark_user_stop "$state" "$task" s2 default:wG6:p2; then
  echo 'directory marker was overwritten'; exit 1
fi
[ -d "$(fm_task_inbox_user_stop_path "$state" "$task")" ] || { echo 'directory marker was removed'; exit 1; }
rmdir "$(fm_task_inbox_user_stop_path "$state" "$task")"
case "$(fm_task_inbox_due_action "$state" "$task")" in
  ring\ *) ;;
  *) echo 'unexpected dead generation did not remain eligible'; exit 1;;
esac
printf 'ok - explicit verified user stop suppresses only the matching generation and preserves unread records\n'
