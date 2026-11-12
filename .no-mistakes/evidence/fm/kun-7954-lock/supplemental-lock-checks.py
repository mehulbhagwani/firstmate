import os
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path.cwd()
evidence = Path('/Users/mehul/.no-mistakes/evidence/01M78H3P9H4KQ49C0BCY980QK2')
source = (root / 'tests/fm-watcher-lock.test.sh').read_text()
prefix = source.split('\ntest_lock_tombstone_tracks_reaper_start_time || exit 1\n', 1)[0]
fd, path = tempfile.mkstemp(prefix='.gate-lock-supplemental-', suffix='.sh', dir=root / 'tests')
os.close(fd)
script = Path(path)
scratch = Path(tempfile.mkdtemp(prefix='.gate-lock-supplemental-', dir=root))
logs = []
try:
    realps = shutil.which('ps')
    (scratch / 'ps').write_text('#!/bin/sh\ncase " $* " in *" lstart="*) exit 1 ;; esac\nexec "' + realps + '" "$@"\n')
    (scratch / 'ps').chmod(0o700)
    cases = [
        ('Unsupported ps supplementary simulation (not live platform proof)',
         'PATH="' + str(scratch) + ':$PATH" test_mac_ps_start_token_normalizes_whitespace', 0),
        ('Existing successor-exited failure isolated with original test',
         'test_watch_replaced_holder_stands_down_after_successor_exits', 1),
    ]
    for name, tail, expected in cases:
        script.write_text(prefix + '\n' + tail + '\n')
        p = subprocess.run(['bash', str(script)], cwd=root, text=True, capture_output=True, timeout=90)
        logs.append(f'{name}\nselector: {tail}\nexit={p.returncode} expected={expected}\n{p.stdout}{p.stderr}')
        print(logs[-1], flush=True)
        assert p.returncode == expected
    # Native host diagnostic: the directory remains open and present, but the
    # shell same-file predicate used by the production watcher rejects it.
    code = 'exec 6<"$1"; rc=0; [ /dev/fd/6 -ef "$1" ] || rc=$?; printf "opened_directory=yes directory_exists=%s same_file_rc=%s\\n" "$([ -d "$1" ] && echo yes)" "$rc"'
    for bash in ('bash', '/bin/bash'):
        p = subprocess.run([bash, '-c', code, '_', str(scratch)], text=True, capture_output=True)
        logs.append(f'Native open-directory identity diagnostic ({bash})\n{p.stdout}{p.stderr}')
        print(logs[-1], flush=True)
finally:
    script.unlink(missing_ok=True)
    shutil.rmtree(scratch)
    (evidence / 'supplemental-lock-checks.log').write_text('\n'.join(logs))
