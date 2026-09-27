#!/usr/bin/env bash
# Regression coverage for starting a worker directly on an existing GitHub PR branch.
set -u

# shellcheck source=tests/fixtures.sh
. "$(dirname "${BASH_SOURCE[0]}")/fixtures.sh"

TMP_ROOT=$(fm_test_tmproot fm-spawn-pr-branch)
PR_URL=https://github.com/acme/demo/pull/42

make_pr_case() {
  local name=$1 state=${2:-OPEN} case_dir home project origin pool fakebin head initial id
  id="pr-follow-$name-r1"
  case_dir="$TMP_ROOT/$name"
  home="$case_dir/home"
  project="$case_dir/project"
  origin="$case_dir/origin.git"
  pool="$case_dir/pool"
  fakebin=$(make_spawn_fakebin "$case_dir/fake")
  mkdir -p "$home/data/$id" "$home/projects" "$home/state" "$home/config"
  printf 'codex\n' > "$home/config/crew-harness"
  fm_test_spawn_brief "$home" "$id" "Update the existing pull request branch."
  git init --quiet -b main "$project"
  printf 'base\n' > "$project/README.md"
  git -C "$project" add README.md
  git -C "$project" -c user.name='Firstmate Tests' -c user.email='tests@example.invalid' commit -qm initial
  git clone --quiet --bare "$project" "$origin"
  git -C "$project" remote add origin "file://$origin"
  initial=$(git -C "$project" rev-parse HEAD)
  git -C "$project" checkout --quiet -b follow-up
  printf 'follow-up\n' >> "$project/README.md"
  git -C "$project" add README.md
  git -C "$project" -c user.name='Firstmate Tests' -c user.email='tests@example.invalid' commit -qm 'existing PR head'
  head=$(git -C "$project" rev-parse HEAD)
  git -C "$project" push --quiet origin follow-up
  git -C "$project" checkout --quiet main
  git -C "$project" config remote.origin.pushurl "https://github.com/acme/demo.git"
  git -C "$project" worktree add --quiet --detach "$pool" "$initial"
  cat > "$fakebin/gh" <<'SH'
#!/usr/bin/env bash
set -u
if [ "${1:-}" = pr ] && [ "${2:-}" = view ]; then
  printf '%s\n' "${FM_FAKE_PR_JSON:?}"
  exit 0
fi
printf 'unexpected gh call: %s\n' "$*" >&2
exit 1
SH
  chmod +x "$fakebin/gh"
  printf '%s|%s|%s|%s|%s|%s|%s|%s\n' \
    "$case_dir" "$home" "$project" "$pool" "$fakebin" "$head" "$initial" "$state"
}

read_case() {
  IFS='|' read -r _CASE_DIR HOME_DIR PROJECT_DIR POOL_DIR FAKEBIN_DIR HEAD_SHA INITIAL_SHA PR_STATE <<EOF
$1
EOF
}

run_pr_spawn() {
  local id=$1
  FM_FAKE_PR_JSON=$(printf '{"state":"%s","headRefName":"follow-up","headRefOid":"%s","headRepositoryOwner":{"login":"acme"},"headRepository":{"name":"demo"}}' "$PR_STATE" "$HEAD_SHA") \
    fm_test_run_spawn "$HOME_DIR" "$POOL_DIR" "$FAKEBIN_DIR" "$id" "$PROJECT_DIR" \
      --mode no-mistakes --yolo off --pr "$PR_URL"
}

test_existing_pr_branch_is_checked_out_and_recorded() {
  local rec id out status upstream
  id=pr-follow-success-r1
  rec=$(make_pr_case success)
  read_case "$rec"
  out=$(run_pr_spawn "$id")
  status=$?
  expect_code 0 "$status" "existing PR branch spawn should succeed"$'\n'"$out"
  [ "$(git -C "$POOL_DIR" branch --show-current)" = follow-up ] \
    || fail "spawn did not check out the PR head branch"
  [ "$(git -C "$POOL_DIR" rev-parse HEAD)" = "$HEAD_SHA" ] \
    || fail "spawn did not check out the forge-reported PR head"
  upstream=$(git -C "$POOL_DIR" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}') \
    || fail "spawn did not configure branch tracking"
  [ "$upstream" = origin/follow-up ] || fail "PR branch tracks '$upstream', not origin/follow-up"
  assert_grep "pr=$PR_URL" "$HOME_DIR/state/$id.meta" "task metadata omitted the PR URL"
  assert_grep "pr_head=$HEAD_SHA" "$HOME_DIR/state/$id.meta" "task metadata omitted the PR head"
  assert_grep "already checked out on the existing pull-request branch" "$HOME_DIR/data/$id/launch-brief.md" \
    "launch instructions did not suppress creation of a duplicate branch"
  pass "an existing PR branch is checked out, tracked, and recorded"
}

test_merged_pr_is_refused() {
  local rec id out status
  id=pr-follow-merged-r1
  rec=$(make_pr_case merged MERGED)
  read_case "$rec"
  out=$(run_pr_spawn "$id")
  status=$?
  [ "$status" -ne 0 ] || fail "merged PR spawn was accepted"
  assert_contains "$out" "merged" "merged PR refusal did not name the merged state"
  [ ! -e "$HOME_DIR/state/$id.meta" ] || fail "merged PR refusal published task metadata"
  pass "a merged PR is refused before launch"
}

test_pr_without_push_remote_is_refused() {
  local rec id out status
  id=pr-follow-no-push-r1
  rec=$(make_pr_case no-push)
  read_case "$rec"
  git -C "$PROJECT_DIR" config --unset-all remote.origin.pushurl
  out=$(run_pr_spawn "$id")
  status=$?
  [ "$status" -ne 0 ] || fail "PR without a usable push remote was accepted"
  assert_contains "$out" "push" "non-pushable PR refusal did not name push access"
  [ ! -e "$HOME_DIR/state/$id.meta" ] || fail "non-pushable PR refusal published task metadata"
  pass "a PR whose head repository is not a push remote is refused"
}

test_local_pr_branch_at_other_commit_is_refused() {
  local rec id out status
  id=pr-follow-conflict-r1
  rec=$(make_pr_case conflict)
  read_case "$rec"
  git -C "$POOL_DIR" branch --force follow-up "$INITIAL_SHA"
  out=$(run_pr_spawn "$id")
  status=$?
  [ "$status" -ne 0 ] || fail "conflicting local PR branch was accepted"
  assert_contains "$out" "different commit" "conflicting local branch refusal did not name the commit mismatch"
  [ ! -e "$HOME_DIR/state/$id.meta" ] || fail "conflicting local branch refusal published task metadata"
  pass "a local PR branch at a different commit is refused"
}

test_existing_pr_branch_is_checked_out_and_recorded
test_merged_pr_is_refused
test_pr_without_push_remote_is_refused
test_local_pr_branch_at_other_commit_is_refused
