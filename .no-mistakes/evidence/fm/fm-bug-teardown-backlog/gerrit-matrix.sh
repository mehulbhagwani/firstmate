
test_gerrit_retention_matrix() {
  local scenario case_dir head revision state rc expected
  for scenario in merged open abandoned stale; do
    case_dir=$(make_case "gerrit-$scenario")
    write_meta "$case_dir" direct-PR ship
    printf '%s\n' 'pr=https://gerrit.example.com/c/project/+/42' >> "$case_dir/state/task-x1.meta"
    wt_commit_file "$case_dir" feature.txt 'reviewed content'
    head=$(git -C "$case_dir/wt" rev-parse HEAD)
    git -C "$case_dir/wt" push -q origin fm/task-x1
    seed_backlog_in_flight "$case_dir"
    revision=$head
    expected=0
    case "$scenario" in
      merged) state=MERGED ;;
      open) state=NEW ;;
      abandoned) state=ABANDONED; expected=1 ;;
      stale) state=MERGED; revision=$(git -C "$case_dir/wt" rev-parse HEAD^); expected=1 ;;
    esac
    add_gh_axi_error "$case_dir"
    cat > "$case_dir/fakebin/gerrit-axi" <<SH
#!/usr/bin/env bash
[ "\$*" = 'show 42 --host gerrit.example.com --json' ] || exit 1
printf '%s\n' '{"ok":true,"changes":[{"change":42,"status":"$state","revision":"$revision"}]}'
SH
    chmod +x "$case_dir/fakebin/gerrit-axi"
    rc=0
    FM_HOME="$case_dir" run_teardown "$case_dir" > "$case_dir/stdout" 2> "$case_dir/stderr" || rc=$?
    expect_code "$expected" "$rc" "Gerrit $scenario: $(cat "$case_dir/stderr")"
    if [ "$expected" = 1 ]; then
      assert_refusal_retained_task_state "$case_dir" "Gerrit $scenario" "$head"
      [ "$(backlog_row_state "$case_dir")" = in_flight ] || fail 'Gerrit refusal closed the backlog'
    else
      assert_absent "$case_dir/state/task-x1.meta" 'Gerrit accepted task was not retired'
      [ "$(backlog_row_state "$case_dir")" = done ] || fail 'Gerrit accepted task backlog was not closed'
    fi
    printf 'Gerrit scenario %s: exit=%s; backlog=%s\n' "$scenario" "$rc" "$(backlog_row_state "$case_dir")"
  done
  pass 'Gerrit accepts merged/current and open/pushed reviews; refuses abandoned and stale merged reviews'
}
fm_test_run test_gerrit_retention_matrix
