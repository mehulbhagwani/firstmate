# Pi Bash timeout validation

Validated the target extension through the installed Pi 1.5.2 CLI using the existing openai-codex login and gpt-6-luna. Each CLI ran on a private tmux socket with a marked disposable Firstmate home. No credential changes, production fleet actions, or external delivery mutations were performed.

## Developer state isolation

With real Pi running, the regression test was executed once sequentially and twice concurrently. Both the existing worktree extension marker and the running Pi marker were preserved byte-for-byte; the running marker modification time was unchanged. Pi subsequently executed the requested Bash commands successfully. See [state-isolation.json](state-isolation.json) and [cap-1000.transcript.jsonl](cap-1000.transcript.jsonl).

## Real Bash results

| Check | Requested timeout | Product output | Product duration |
| --- | --- | --- | --- |
| omitted-and-steering | omitted | START /  / Command timed out after 1 seconds | 1.005 s |
| larger-explicit | 60 | Command timed out after 1 seconds | 1.004 s |
| shorter-explicit | 0.2 | Command timed out after 0.2 seconds | 0.204 s |
| equal-explicit | 1 | Command timed out after 1 seconds | 1.011 s |
| quick-command | omitted | QUICK_WORKS | 0.003 s |
| subsecond | omitted | Command timed out after 0.5 seconds | 0.507 s |
| minimum | omitted | Command timed out after 0.001 seconds | 0.005 s |
| maximum-omitted | omitted | MAXIMUM_WORKS | 0.006 s |
| maximum-explicit | 2147483.648 | MAXIMUM_CLAMPS | 0.005 s |
| oversized-setting | omitted | OVERSIZED_IGNORED | 0.006 s |
| oversized-preserves-explicit | 0.2 | Command timed out after 0.2 seconds | 0.206 s |
| leading-zero-ignored | omitted | INVALID_IGNORED | 1.369 s |
| unset-default | omitted | DEFAULT_WORKS | 1.289 s |
| unset-explicit | 0.2 | Command timed out after 0.2 seconds | 0.206 s |
| worker-unaffected | omitted | WORKER_WORKS | 1.365 s |

Two steering messages queued while the omitted-timeout command was running were acknowledged after its one-second timeout. The runtime emitted optional timeout as null for some model calls and normalized it before execution; the real cap still applied.

## Commands and evidence

- `bin/fm-test-run.sh tests/fm-pi-bash-timeout.test.sh` passed.
- `python3 pi-live-check.py` drove the live scenarios; the script is retained beside this report.
- The live CLI used `pi --mode rpc --no-session --no-extensions --no-skills --no-prompt-templates --no-themes --no-context-files --no-mcp --offline --provider openai-codex --model gpt-6-luna --thinking low --tools bash`, with the target extension explicitly loaded except for the worker-boundary scenario.
- Each transcript records the exact launch command, requested input, returned events, extension identity, and cleanup. Raw `*.rpc.jsonl` files retain Pi output.
- `gh-axi pr view 8445 --repo kunchenguid/firstmate --fields url,state,headRefOid,closingIssuesReferences` confirms GitHub recognizes issue #7608 as a closing reference. See [pr-delivery-state.txt](pr-delivery-state.txt).

## Delivery boundary

PR https://github.com/kunchenguid/firstmate/pull/8445 is open and has the issue-closing reference. Its observed head is 8db4010ccf59842c72c6869bafc6c9f704d2ac82. Re-raising with this run target ac4fd39d2aa9550b7a2ea2883016ac1dff36d798 and refreshing the attestation are outside the assigned test phase and remain with the outer executor.

## Setup and cleanup

The first private-socket attempt needed its parent directory created. Subsequent driver setup was corrected to truncate reused output before startup and preserve an already-existing worktree marker. A driver-only assertion was corrected to accept the runtime representation of an omitted optional timeout as null. All scenarios were then re-driven successfully; no product source changes were needed.

All eight final live sessions record successful cleanup. No rendered UI or copy placement changed, so product evidence consists of CLI transcripts and persisted marker observations rather than screenshots.

- [cap-1.transcript.jsonl](cap-1.transcript.jsonl)
- [cap-1000.transcript.jsonl](cap-1000.transcript.jsonl)
- [cap-500.transcript.jsonl](cap-500.transcript.jsonl)
- [cap-invalid.transcript.jsonl](cap-invalid.transcript.jsonl)
- [cap-maximum.transcript.jsonl](cap-maximum.transcript.jsonl)
- [cap-oversized.transcript.jsonl](cap-oversized.transcript.jsonl)
- [cap-unset.transcript.jsonl](cap-unset.transcript.jsonl)
- [without-extension.transcript.jsonl](without-extension.transcript.jsonl)

The two transient discovery markers created by the initial `pi --help` capability probe were removed after validating their unchanged contents; the temporary worktree state directory was removed. The final source diff is empty.
