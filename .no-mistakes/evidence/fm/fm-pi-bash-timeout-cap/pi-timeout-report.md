# Pi Bash timeout live verification

Verdict: no-go. Ordinary cap behavior and queued steering work; a documented-valid configuration above Pi's native timer maximum prevents Bash execution.

## Environment and method

- Source: target `43f773473eb778fabc59d0f7a85f926275b3298e`; control extension from base `427056c4181c41074ad24f051f79919330df0fa5`.
- Installed Pi `1.5.2`, provider/model `openai-codex/gpt-6.1-sol`, normal existing authentication; no mocked model, tool, extension API, or shell.
- Real Pi CLI in RPC mode launched as the session command on a private tmux socket. Every session used a marked disposable lab home and the target extension explicitly loaded, except the named no-extension and base-control cases.
- Commands were bounded sleeps and printf, exercising the actual Bash tool without searching personal directories or waiting for a multi-minute stall.
- RPC model tool calls, tool outputs, durationMs, queue acknowledgements, and final replies were captured. Pi emits `timeout: null` for omitted optional arguments in the provider call; the real tool path normalizes it and the cap demonstrably takes effect.
- No rendered UI was changed; CLI transcripts are the product evidence.

## Focused baseline check

`bash tests/fm-pi-bash-timeout.test.sh` passed. This exercises the callback with a stub API and is supplemental, not live evidence.

## Live results

| Case | Configuration (ms) | Requested timeout (seconds) | Actual tool duration (ms) | Observed result |
| --- | --- | --- | --- | --- |
| omitted-timeout-and-steering | 5000 | omitted | 5009 | SHELL_STARTED /  /  / Command timed out after 5 seconds |
| explicit-60-capped | 5000 | 60 | 5003 | SHELL_STARTED /  /  / Command timed out after 5 seconds |
| explicit-1-preserved | 5000 | 1 | 1005 | SHELL_STARTED /  /  / Command timed out after 1 seconds |
| explicit-5-preserved | 5000 | 5 | 5005 | SHELL_STARTED /  /  / Command timed out after 5 seconds |
| quick-command-completes | 5000 | omitted | 178 | SHELL_STARTED / SHELL_FINISHED /  |
| subsecond-omitted | 500 | omitted | 507 | SHELL_STARTED /  /  / Command timed out after 0.5 seconds |
| subsecond-explicit-capped | 500 | 1 | 509 | SHELL_STARTED /  /  / Command timed out after 0.5 seconds |
| subsecond-shorter-preserved | 500 | 0.2 | 204 | SHELL_STARTED /  /  / Command timed out after 0.2 seconds |
| unset-no-timeout (initial input had an extra unused printf argument; superseded by unset-exact-command) | unset | omitted | 1025 | SHELL_STARTED / SHELL_FINISHED /  |
| unset-explicit-preserved | unset | 0.2 | 204 | SHELL_STARTED /  /  / Command timed out after 0.2 seconds |
| invalid-zero | 0 | omitted | 1031 | SHELL_STARTED / SHELL_FINISHED /  |
| invalid-text | invalid | omitted | 1088 | SHELL_STARTED / SHELL_FINISHED /  |
| invalid-leading-zero | 0500 | omitted | 1080 | SHELL_STARTED / SHELL_FINISHED /  |
| invalid-unsafe-integer | 9007199254740992 | omitted | 1036 | SHELL_STARTED / SHELL_FINISHED /  |
| unset-exact-command | unset | omitted | 1020 | SHELL_STARTED / SHELL_FINISHED /  |
| worker-without-extension-unchanged | 500 | omitted | 1086 | SHELL_STARTED / SHELL_FINISHED /  |
| pre-fix-omitted-outlives-cap | 5000 | omitted | 7018 | SHELL_STARTED / SHELL_FINISHED /  |
| native-maximum-accepted | 2147483647 | omitted | 5 | SHELL_FINISHED /  |
| documented-valid-cap-above-native-limit | 2147483648 | omitted | 2 | Invalid timeout: maximum is 2147483.647 seconds |

## Queued steering and regression control

### pre-fix-omitted-outlives-cap

Actual Bash duration: 7018 ms. Both steering requests were accepted with `disposition: queued` while the Bash call was active.

Tool output:
```text
SHELL_STARTED
SHELL_FINISHED

```

Final Pi reply:
```text
Tool output:
```text
SHELL_STARTED
SHELL_FINISHED
```

STEERING_ONE_RECEIVED
STEERING_TWO_RECEIVED
```

### omitted-timeout-and-steering

Actual Bash duration: 5009 ms. Both steering requests were accepted with `disposition: queued` while the Bash call was active.

Tool output:
```text
SHELL_STARTED


Command timed out after 5 seconds
```

Final Pi reply:
```text
The command printed `SHELL_STARTED`, then timed out after 5 seconds. `SHELL_FINISHED` was not printed.

STEERING_ONE_RECEIVED
STEERING_TWO_RECEIVED
```

The pre-fix control completed its full seven-second command despite the five-second opt-in setting, keeping steering queued until that command returned. The target stopped the ten-second command after five seconds and then acknowledged both messages.

## Reproducible boundary failure

1. Launch the real Pi CLI with the target extension and `FM_PI_BASH_TIMEOUT_MAX_MS=2147483647`.
2. Ask its Bash tool to run `printf` without a timeout. It prints `SHELL_FINISHED`.
3. Change only the configured value to `2147483648`, still a positive decimal safe integer under the documented contract.
4. The same command does not execute. Pi returns `Invalid timeout: maximum is 2147483.647 seconds` in 2 ms.

The extension accepts the value and injects a timeout beyond the native tool's maximum. This is a product failure, not a missing credential or lab setup issue. Bound the setting to the supported timer range (or reject unsupported values), update the documented range, and cover it through the executable tool path.

## Exact commands

```sh
bash tests/fm-pi-bash-timeout.test.sh
python3 /Users/mehul/.no-mistakes/evidence/01M7B6EEDS5Y9FD8BQFR9QDJ38/pi-timeout-live.py
python3 /Users/mehul/.no-mistakes/evidence/01M7B6EEDS5Y9FD8BQFR9QDJ38/pi-timeout-boundaries.py
```

The first live batch passed. The boundary driver exited 1 on the real tool error above. The reusable driver was tightened afterward to require exact model arguments and use Pi's own durationMs; the one inconsequential initial input deviation was repeated exactly and passed. No source or test files were changed.

## Cleanup

Every private tmux server was stopped through its own socket; the supported lab cleanup removed each private socket directory. All marked lab homes and the temporary base extension were removed. Evidence remains in this directory.
