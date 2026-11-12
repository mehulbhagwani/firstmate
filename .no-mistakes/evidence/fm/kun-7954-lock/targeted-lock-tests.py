import os
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path.cwd()
evidence = Path('/Users/mehul/.no-mistakes/evidence/01M78H3P9H4KQ49C0BCY980QK2')
source = (root / 'tests/fm-watcher-lock.test.sh').read_text()
# The suite has no selector. Retain its complete setup and function definitions,
# replace only the bottom invocation list, and execute the unmodified functions.
prefix = source.split('\ntest_lock_tombstone_tracks_reaper_start_time || exit 1\n', 1)[0]
fd, path = tempfile.mkstemp(prefix='.gate-lock-selected-', suffix='.sh', dir=root / 'tests')
os.close(fd)
script = Path(path)
scratch = Path(tempfile.mkdtemp(prefix='.gate-lock-tests-', dir=root))
logs = []

def execute(label, tail, env=None, expected=0, bash='bash', timeout=100):
    script.write_text(prefix + '\n' + tail + '\n')
    p = subprocess.run([bash, str(script)], cwd=root, env=env, text=True, capture_output=True, timeout=timeout)
    text = f'{label}\ncommand: {bash} <original suite setup/functions + named selector>\nselectors:\n{tail}\nexit={p.returncode} expected={expected}\n{p.stdout}{p.stderr}'
    print(text, flush=True)
    logs.append(text)
    (evidence / 'targeted-lock-tests.log').write_text('\n'.join(logs))
    assert p.returncode == expected, label

try:
    execute('Targeted changed lock tests', '\n'.join([
        'test_lock_reclaims_reused_pid_but_not_a_live_owner',
        'test_lock_bounded_acquire_reused_pid_under_live_stealer',
        'test_mac_ps_start_token_normalizes_whitespace',
        'test_lock_start_record_matches_probe',
        'test_lock_respects_live_holder_matching_its_start_time',
        'test_lock_reclaims_reused_pid_lock',
        'test_lock_live_steal_mutex_is_not_reclaimed',
    ]))
    execute('Stock macOS Bash changed tests', '\n'.join([
        'test_lock_reclaims_reused_pid_but_not_a_live_owner',
        'test_lock_bounded_acquire_reused_pid_under_live_stealer',
        'test_mac_ps_start_token_normalizes_whitespace',
        'test_lock_start_record_matches_probe',
    ]), bash='/bin/bash')
    basebin = scratch / 'base/bin'
    basebin.mkdir(parents=True)
    for filename in ['fm-wake-lib.sh', 'fm-path-lib.sh', 'fm-timeout-lib.sh']:
        p = subprocess.run(['git', 'show', '095db3bc7e57b4d50b7e2ac66f9671ba66be692b:bin/' + filename], cwd=root, capture_output=True, text=True, check=True)
        (basebin / filename).write_text(p.stdout)
    execute('Regression counterfactual with base production lock libraries',
            'LIB="' + str(basebin / 'fm-wake-lib.sh') + '"\ntest_lock_bounded_acquire_reused_pid_under_live_stealer', expected=1)
    fakebin = scratch / 'unsupported-ps'
    fakebin.mkdir()
    realps = shutil.which('ps')
    (fakebin / 'ps').write_text('#!/bin/sh\ncase " $* " in *" lstart="*) exit 1 ;; esac\nexec "' + realps + '" "$@"\n')
    (fakebin / 'ps').chmod(0o700)
    env = dict(os.environ, PATH=str(fakebin) + ':' + os.environ['PATH'])
    execute('Supplementary simulated unsupported ps capability (not live platform proof)',
            'test_mac_ps_start_token_normalizes_whitespace', env=env)
    execute('Reproduce existing successor-exited failure independently',
            'test_watch_replaced_holder_stands_down_after_successor_exits', expected=1)
finally:
    script.unlink(missing_ok=True)
    shutil.rmtree(scratch)
    (evidence / 'targeted-lock-tests.log').write_text('\n'.join(logs))
