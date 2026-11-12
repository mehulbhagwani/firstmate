import os
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path.cwd()
evidence = Path('/Users/mehul/.no-mistakes/evidence/01M78H3P9H4KQ49C0BCY980QK2')
source = (root / 'tests/fm-watcher-lock.test.sh').read_text()
# Retain the suite setup/functions to override only the library path for the base counterfactual. No assertions inspect implementation source.
prefix = source.split('\ntest_lock_tombstone_tracks_reaper_start_time || exit 1\n', 1)[0]
fd, path = tempfile.mkstemp(prefix='.gate-lock-selected-', suffix='.sh', dir=root / 'tests')
os.close(fd)
script = Path(path)
scratch = Path(tempfile.mkdtemp(prefix='.gate-lock-tests-', dir=root))
logs = []
os.environ['TMPDIR'] = str(scratch)
os.environ['FM_TEST_SKIP_ORPHAN_REAP'] = '1'

def execute(label, tail, env=None, expected=0, bash='bash', timeout=100):
    script.write_text(prefix + '\n' + tail + '\n')
    p = subprocess.run([bash, str(script)], cwd=root, env=env, text=True, capture_output=True, timeout=timeout)
    text = f'{label}\ncommand: {bash} <original suite setup/functions + named selector>\nselectors:\n{tail}\nexit={p.returncode} expected={expected}\n{p.stdout}{p.stderr}'
    print(text, flush=True)
    logs.append(text)
    (evidence / 'round3-targeted-lock-tests.log').write_text('\n'.join(logs))
    assert p.returncode == expected, label

try:
    execute('Stock macOS Bash changed tests', '\n'.join([
        'test_lock_reclaims_reused_pid_but_not_a_live_owner',
        'test_lock_bounded_acquire_reused_pid_under_live_stealer',
        'test_mac_ps_start_token_normalizes_whitespace',
        'test_lock_start_record_matches_probe',
    ]), bash='/bin/bash')
    basebin = scratch / 'base/bin'
    basebin.mkdir(parents=True)
    for filename in ['fm-wake-lib.sh', 'fm-path-lib.sh', 'fm-timeout-lib.sh']:
        p = subprocess.run(['git', 'show', 'a9ae3c0c673bd98ecafdab52fc130a13621fb7af:bin/' + filename], cwd=root, capture_output=True, text=True, check=True)
        (basebin / filename).write_text(p.stdout)
    execute('Regression counterfactual with base production lock libraries',
            'LIB="' + str(basebin / 'fm-wake-lib.sh') + '"\ntest_lock_bounded_acquire_reused_pid_under_live_stealer', expected=1)

finally:
    script.unlink(missing_ok=True)
    shutil.rmtree(scratch)
    (evidence / 'round3-targeted-lock-tests.log').write_text('\n'.join(logs))
