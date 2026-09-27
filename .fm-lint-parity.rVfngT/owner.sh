#!/usr/bin/env bash
# shellcheck source=.fm-lint-parity.rVfngT/owner-dep.sh
. "/Users/rac/.no-mistakes/worktrees/ba74ac5033c4/01M3JBRZRG9SEA1B04B51JXWFH/.fm-lint-parity.rVfngT/owner-dep.sh"
owner_bad() {
  printf '%s\n' "$owner_dependency_value"
  cd "$1"
}
