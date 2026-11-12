import os
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path.cwd()
evidence=Path('/Users/mehul/.no-mistakes/evidence/01M78H3P9H4KQ49C0BCY980QK2')
scratch=Path(tempfile.mkdtemp(prefix='.gate-ps-capability-',dir=root))
fd,name=tempfile.mkstemp(prefix='.gate-ps-capability-',suffix='.sh',dir=root/'tests')
os.close(fd)
script=Path(name)
try:
    realps=shutil.which('ps')
    # Deterministic capability simulation, not a live unsupported-ps host.
    # Preserve native token queries in the /proc leg so macOS can exercise the
    # same leg ordering as a host that has /proc but lacks the ps fallback.
    (scratch/'ps').write_text('''#!/bin/sh
case " $* " in
  *" lstart="*)
    printf '%s\\n' "${FM_PROC_ROOT_OVERRIDE:-capability-preflight}" >> "$PS_CALL_LOG"
    [ "${FM_PROC_ROOT_OVERRIDE:-}" = /proc ] || exit 1
    ;;
esac
exec "'''+realps+'''" "$@"
''')
    (scratch/'ps').chmod(0o700)
    prefix=(root/'tests/fm-watcher-lock.test.sh').read_text().split('\ntest_lock_tombstone_tracks_reaper_start_time || exit 1\n',1)[0]
    # Apply the capability simulation after native test initialization, which
    # itself needs host ps to register safely bounded fixture cleanup.
    script.write_text(prefix+'''
export PATH="$PS_SIM_DIR:$PATH"
test_mac_ps_start_token_normalizes_whitespace
test_lock_start_record_matches_probe
''')
    calls=scratch/'calls.log'
    env=dict(os.environ,TMPDIR=str(scratch),FM_TEST_SKIP_ORPHAN_REAP='1',PS_SIM_DIR=str(scratch),PS_CALL_LOG=str(calls))
    result=subprocess.run(['bash',str(script)],cwd=root,env=env,text=True,capture_output=True,timeout=45)
    trace=calls.read_text().splitlines()
    report=f'Supplementary unsupported-ps capability simulation; not live platform proof.\nSetup corrected: apply PATH shim only after native test initialization.\nSelectors: test_mac_ps_start_token_normalizes_whitespace; test_lock_start_record_matches_probe\nexit={result.returncode}\n{result.stdout}{result.stderr}\nps lstart request contexts: {trace}\n'
    print(report)
    (evidence/'round3-unsupported-ps.log').write_text(report)
    assert result.returncode==0
    assert trace.count('capability-preflight')==2
    assert '/proc' in trace and all(x in ('capability-preflight','/proc') for x in trace)
finally:
    script.unlink(missing_ok=True)
    shutil.rmtree(scratch)
