# Pi Bash timeout live validation

Target: `8db4010ccf59842c72c6869bafc6c9f704d2ac82`. Runtime: Pi 1.5.2, normal existing openai-codex login, real Bash tool.

All nine target scenarios passed. Seventeen target Bash calls and two historical comparison calls were driven through real Pi RPC sessions on private tmux sockets. The focused executable regression test `bin/fm-test-run.sh tests/fm-pi-bash-timeout.test.sh` also passed (exit 0, no skips).

The long-command reproduction used bounded sleeps in place of home-wide discovery. The base version ran for 8.279 seconds despite a configured 5-second cap; the target stopped after 5.153 seconds. The version immediately before the boundary fix rejected an ordinary printf at setting 2147483648; the target executed that identical printf successfully.

No terminal UI was changed. Product evidence is the real CLI request, execution events, output, duration, steering queue, and reply. No stubs or mock tools were used for the live scenarios.

## Isolation and cleanup

Each session used a disposable home created with `bin/fm-lab-home.sh create`, the helper-owned private tmux directory, explicit `tmux -S` addressing, and the extension from this run's source. Global extension discovery, context files, MCP, saved sessions, telemetry, and startup network operations were disabled. Normal existing credentials were used without login changes. An initial private-socket setup attempt lacked its parent directory; the driver created it and reran successfully. All successful sessions have cleanup receipts. The two historical extension snapshots were temporary files beside the target extension so their relative imports and script paths remained genuine; those files were removed. No source or test changes remain.

## Exact commands and results

### cap-5000-retry

Setting: `5000`. Extension loaded: `True`.

Raw product stream: [cap-5000-retry.jsonl](cap-5000-retry.jsonl). Timestamped requests and events: [cap-5000-retry.transcript.jsonl](cap-5000-retry.transcript.jsonl).

#### omitted-timeout

Requested Bash input:
```json
{
  "command": "printf CAP_START; sleep 8; printf SHOULD_NOT_FINISH"
}
```

Product output:
```text
CAP_START

Command timed out after 5 seconds
```
Tool duration: 5153 ms. Tool reported error: True. Pi settled: True.

#### oversized-explicit

Requested Bash input:
```json
{
  "command": "printf EXPLICIT_START; sleep 8; printf SHOULD_NOT_FINISH",
  "timeout": 60
}
```

Product output:
```text
EXPLICIT_START

Command timed out after 5 seconds
```
Tool duration: 5476 ms. Tool reported error: True. Pi settled: True.

#### shorter-explicit

Requested Bash input:
```json
{
  "command": "printf SHORT_START; sleep 3; printf SHOULD_NOT_FINISH",
  "timeout": 1
}
```

Product output:
```text
SHORT_START

Command timed out after 1 seconds
```
Tool duration: 1009 ms. Tool reported error: True. Pi settled: True.

#### equal-explicit

Requested Bash input:
```json
{
  "command": "printf EQUAL_START; sleep 6; printf SHOULD_NOT_FINISH",
  "timeout": 5
}
```

Product output:
```text
EQUAL_START

Command timed out after 5 seconds
```
Tool duration: 5004 ms. Tool reported error: True. Pi settled: True.

Cleanup: True.

### cap-subsecond

Setting: `500`. Extension loaded: `True`.

Raw product stream: [cap-subsecond.jsonl](cap-subsecond.jsonl). Timestamped requests and events: [cap-subsecond.transcript.jsonl](cap-subsecond.transcript.jsonl).

#### subsecond-default

Requested Bash input:
```json
{
  "command": "printf SUBSECOND_START; sleep 2; printf SHOULD_NOT_FINISH"
}
```

Product output:
```text
SUBSECOND_START

Command timed out after 0.5 seconds
```
Tool duration: 508 ms. Tool reported error: True. Pi settled: True.

#### subsecond-explicit

Requested Bash input:
```json
{
  "command": "printf SUBSECOND_EXPLICIT; sleep 2; printf SHOULD_NOT_FINISH",
  "timeout": 1
}
```

Product output:
```text
SUBSECOND_EXPLICIT

Command timed out after 0.5 seconds
```
Tool duration: 505 ms. Tool reported error: True. Pi settled: True.

Cleanup: True.

### cap-minimum

Setting: `1`. Extension loaded: `True`.

Raw product stream: [cap-minimum.jsonl](cap-minimum.jsonl). Timestamped requests and events: [cap-minimum.transcript.jsonl](cap-minimum.transcript.jsonl).

#### minimum-cap

Requested Bash input:
```json
{
  "command": "sleep 1; printf SHOULD_NOT_FINISH"
}
```

Product output:
```text
Command timed out after 0.001 seconds
```
Tool duration: 6 ms. Tool reported error: True. Pi settled: True.

Cleanup: True.

### cap-maximum

Setting: `2147483647`. Extension loaded: `True`.

Raw product stream: [cap-maximum.jsonl](cap-maximum.jsonl). Timestamped requests and events: [cap-maximum.transcript.jsonl](cap-maximum.transcript.jsonl).

#### maximum-supported

Requested Bash input:
```json
{
  "command": "printf MAXIMUM_WORKS"
}
```

Product output:
```text
MAXIMUM_WORKS
```
Tool duration: 7 ms. Tool reported error: False. Pi settled: True.

#### maximum-clamps-native-invalid

Requested Bash input:
```json
{
  "command": "printf MAXIMUM_CLAMPS",
  "timeout": 2147483.648
}
```

Product output:
```text
MAXIMUM_CLAMPS
```
Tool duration: 58 ms. Tool reported error: False. Pi settled: True.

Cleanup: True.

### cap-above-maximum

Setting: `2147483648`. Extension loaded: `True`.

Raw product stream: [cap-above-maximum.jsonl](cap-above-maximum.jsonl). Timestamped requests and events: [cap-above-maximum.transcript.jsonl](cap-above-maximum.transcript.jsonl).

#### above-maximum-ignored

Requested Bash input:
```json
{
  "command": "printf ABOVE_MAXIMUM_WORKS"
}
```

Product output:
```text
ABOVE_MAXIMUM_WORKS
```
Tool duration: 14 ms. Tool reported error: False. Pi settled: True.

#### above-maximum-preserves-explicit

Requested Bash input:
```json
{
  "command": "printf RETAINED_TIMEOUT; sleep 1; printf SHOULD_NOT_FINISH",
  "timeout": 0.2
}
```

Product output:
```text
RETAINED_TIMEOUT

Command timed out after 0.2 seconds
```
Tool duration: 204 ms. Tool reported error: True. Pi settled: True.

Cleanup: True.

### cap-invalid-leading-zero

Setting: `01`. Extension loaded: `True`.

Raw product stream: [cap-invalid-leading-zero.jsonl](cap-invalid-leading-zero.jsonl). Timestamped requests and events: [cap-invalid-leading-zero.transcript.jsonl](cap-invalid-leading-zero.transcript.jsonl).

#### invalid-leading-zero

Requested Bash input:
```json
{
  "command": "printf INVALID_START; sleep 1; printf INVALID_FINISHED"
}
```

Product output:
```text
INVALID_STARTINVALID_FINISHED
```
Tool duration: 1122 ms. Tool reported error: False. Pi settled: True.

Cleanup: True.

### cap-unsafe-integer

Setting: `9007199254740992`. Extension loaded: `True`.

Raw product stream: [cap-unsafe-integer.jsonl](cap-unsafe-integer.jsonl). Timestamped requests and events: [cap-unsafe-integer.transcript.jsonl](cap-unsafe-integer.transcript.jsonl).

#### unsafe-integer-ignored

Requested Bash input:
```json
{
  "command": "printf UNSAFE_INTEGER_WORKS"
}
```

Product output:
```text
UNSAFE_INTEGER_WORKS
```
Tool duration: 40 ms. Tool reported error: False. Pi settled: True.

Cleanup: True.

### cap-unset

Setting: `unset`. Extension loaded: `True`.

Raw product stream: [cap-unset.jsonl](cap-unset.jsonl). Timestamped requests and events: [cap-unset.transcript.jsonl](cap-unset.transcript.jsonl).

#### default-off

Requested Bash input:
```json
{
  "command": "printf DEFAULT_START; sleep 1; printf DEFAULT_FINISHED"
}
```

Product output:
```text
DEFAULT_STARTDEFAULT_FINISHED
```
Tool duration: 1089 ms. Tool reported error: False. Pi settled: True.

#### default-explicit

Requested Bash input:
```json
{
  "command": "sleep 1; printf SHOULD_NOT_FINISH",
  "timeout": 0.2
}
```

Product output:
```text
Command timed out after 0.2 seconds
```
Tool duration: 207 ms. Tool reported error: True. Pi settled: True.

Cleanup: True.

### cap-unset-long

Setting: `unset`. Extension loaded: `True`.

Raw product stream: [cap-unset-long.jsonl](cap-unset-long.jsonl). Timestamped requests and events: [cap-unset-long.transcript.jsonl](cap-unset-long.transcript.jsonl).

#### opt-out-exceeds-five-seconds

Requested Bash input:
```json
{
  "command": "printf OPT_OUT_START; sleep 8; printf OPT_OUT_FINISHED"
}
```

Product output:
```text
OPT_OUT_STARTOPT_OUT_FINISHED
```
Tool duration: 8083 ms. Tool reported error: False. Pi settled: True.

Cleanup: True.

### worker-no-extension

Setting: `500`. Extension loaded: `False`.

Raw product stream: [worker-no-extension.jsonl](worker-no-extension.jsonl). Timestamped requests and events: [worker-no-extension.transcript.jsonl](worker-no-extension.transcript.jsonl).

#### worker-unaffected

Requested Bash input:
```json
{
  "command": "printf WORKER_START; sleep 1; printf WORKER_FINISHED"
}
```

Product output:
```text
WORKER_STARTWORKER_FINISHED
```
Tool duration: 1278 ms. Tool reported error: False. Pi settled: True.

Cleanup: True.

### base-no-cap

Setting: `5000`. Extension loaded: `True`.

Raw product stream: [base-no-cap.jsonl](base-no-cap.jsonl). Timestamped requests and events: [base-no-cap.transcript.jsonl](base-no-cap.transcript.jsonl).

#### base-omitted-timeout-exceeds-cap

Requested Bash input:
```json
{
  "command": "printf BASE_START; sleep 8; printf BASE_EXCEEDED_CAP"
}
```

Product output:
```text
BASE_STARTBASE_EXCEEDED_CAP
```
Tool duration: 8279 ms. Tool reported error: False. Pi settled: True.

Cleanup: True.

### before-boundary-fix

Setting: `2147483648`. Extension loaded: `True`.

Raw product stream: [before-boundary-fix.jsonl](before-boundary-fix.jsonl). Timestamped requests and events: [before-boundary-fix.transcript.jsonl](before-boundary-fix.transcript.jsonl).

#### previous-boundary-rejection

Requested Bash input:
```json
{
  "command": "printf ABOVE_MAXIMUM_WORKS"
}
```

Product output:
```text
Invalid timeout: maximum is 2147483.647 seconds
```
Tool duration: 4 ms. Tool reported error: True. Pi settled: True.

Cleanup: True.

## Queued steering during the capped call

```json
{"type": "queue_update", "steering": ["After the running command returns, acknowledge STEERING_ONE. Do not retry or run other commands."], "followUp": []}
```

```json
{"type": "queue_update", "steering": ["After the running command returns, acknowledge STEERING_ONE. Do not retry or run other commands.", "Also acknowledge STEERING_TWO. Do not retry or run other commands."], "followUp": []}
```

```json
{"type": "queue_update", "steering": ["Also acknowledge STEERING_TWO. Do not retry or run other commands."], "followUp": []}
```

```json
{"type": "queue_update", "steering": [], "followUp": []}
```

Final assistant reply after the timed-out tool:
```text
The command printed `CAP_START`, then timed out after 5 seconds. No retry was attempted.

Acknowledged STEERING_ONE and STEERING_TWO.
```

## Reproduction drivers

- [drive-pi.py](drive-pi.py): real Pi RPC driver and private-session cleanup.
- [run-matrix.py](run-matrix.py): exact target inputs for configuration, boundary, and worker cases.
- [reproduce-before-fix.py](reproduce-before-fix.py): historical comparison sources and the opt-out long-command case.
