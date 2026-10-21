# PR #7347 live validation (test step, run 01M5F7SRW16SZYPJKBH37QXZY0)

Real bin/fm-pr-merge.sh at 7a4a1be2, run in a throwaway lab home against real GitHub.
guard-bin/gh and guard-bin/gh-axi pass reads through to the real gh and refuse every
mutation locally (exit 97). No merge, comment, or API write ever reached GitHub; see each case's gh-calls.log.

| Case | Target | Live? | Result |
| --- | --- | --- | --- |
| live-green-cli-14716 | cli/cli trunk (protected, 3 classic required builds, all green) | live | verified; merge call blocked by the guard |
| live-never-reported-cli-14727 | cli/cli trunk, PR whose required builds never ran | live | refused: names all 3 unreported required checks; no merge attempted |
| hybrid-null-after | same as 14716, real branch payload with required_status_checks set to null | hybrid | verified (fix treats null as empty) |
| hybrid-null-before | same, run with base 2c93247f scripts | hybrid | refused as unreadable (reproduces #7343) |
| hybrid-missing-protection / missing-required-key / nonobject (after) | same | hybrid | refused as unreadable |

public-branch-shape-scan.txt: of 200 public repos' default branches, 143 are protected and none returns a null
classic required_status_checks, so the null and unreadable shapes could not be found on the live forge.
