#!/usr/bin/env bash
# usage: eval.sh <prompt-file> <outfile>
P=$1; OUT=$2; : > "$OUT"
run() {
  name=$1; ev=$2
  msg="Fleet wake (supervision host; report surface: bin/fm-branch-report.sh command). EVALUATION MODE: tools are unavailable in this turn; assume drain, lease, and crew-state already ran and returned the facts below. Reply with ONLY one JSON object {\"task\":...,\"verdict\":\"routine|captain\",\"silent\":true|false,\"summary\":...} that you would pass to the report surface.

Drained records:
$ev"
  r=$(cd "$(mktemp -d)" && claude -p --model sonnet --tools "" --system-prompt-file "$P" "$msg" 2>&1 | tr '\n' ' ')
  printf '%s\t%s\n' "$name" "$r" >> "$OUT"
}
run failure-to-start "task fix-login (captain-requested: 'fix the login redirect bug'): status line 'blocked: worker failed to start - harness exited 1 before first prompt (auth error: model not found)'. crew-state: pane dead, no commits, no worktree changes. Previous outcome for this task: 'spawned, starting'. Relaunch per playbook already tried once and failed identically."
run meaningful-completion "task docs-search (captain-requested scout: 'find why search is slow'): status line 'done: scout report written - root cause is N+1 query in SearchIndex.load; recommended fix attached'. crew-state: worker idle, report file present. Previous outcome: 'still investigating'."
run actionable-blocker "task api-v2 (captain-requested: 'add v2 endpoint'): status line 'blocked: upstream repo requires a DB migration that conflicts with migration 0042 owned by another team; need direction'. crew-state: worker waiting at prompt."
run review-finding "task cache-fix (captain-requested): status line 'note: validation gate review found a correctness bug - cache key omits tenant id, cross-tenant data leak possible; fixing'. crew-state: worker busy editing."
run unchanged-progress "task cache-fix (captain-requested): status line 'working: still running tests'. crew-state: worker busy, same as last check. Previous outcome for this task (2 minutes ago): 'worker still running tests'. No new commits, no new artifacts, no action taken by you."
run start-update "task refactor-io (captain-requested): status line 'working: started, reading the codebase'. crew-state: worker busy. Previous outcome: none. No action taken."
