import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

ROOT = Path.cwd()
EVIDENCE = Path('/Users/mehul/.no-mistakes/evidence/01M78H3P9H4KQ49C0BCY980QK2')
LIB = str(ROOT / 'bin/fm-wake-lib.sh')
BASH = shutil.which('bash')
BASE_ENV = {k: v for k, v in os.environ.items() if not k.startswith('FM_') and k not in ('STATE', 'CONFIG', 'DATA', 'PROJECTS', 'TASKS_AXI_FILE', 'TASKS_AXI_BACKEND')}
SANDBOX = Path(tempfile.mkdtemp(prefix='.fm-lock-live-', dir=ROOT))
PROCESSES = []
TRANSCRIPT = []
RESULTS = []

def log(text):
    print(text, flush=True)
    TRANSCRIPT.append(text)

def run(args, env, timeout=20):
    start = time.monotonic()
    p = subprocess.run(args, env=env, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    log('$ ' + ' '.join(map(str, args)))
    log(f'exit={p.returncode} elapsed={time.monotonic()-start:.3f}s\nstdout:\n{p.stdout}stderr:\n{p.stderr}')
    return p

def shell(code, env, *args, bash=BASH):
    return run([bash, '-c', code, '_', LIB, *map(str, args)], env)

def lab(name):
    home = SANDBOX / name
    p = run(['bash', 'bin/fm-lab-home.sh', 'create', str(home)], BASE_ENV)
    assert p.returncode == 0
    env = dict(BASE_ENV, FM_HOME=str(home), FM_STATUS_PRESENTATION_LOCK_TIMEOUT='1')
    return home, env

def holder(lock, env):
    ready = Path(str(lock) + '.ready')
    release = Path(str(lock) + '.release')
    p = subprocess.Popen([BASH, '-c', '''
. "$1"
fm_lock_try_acquire "$2" || exit 7
fm_current_pid own
printf 'owner=%s start=%s\n' "$own" "$(cat "$2/pid-start")" > "$3"
while [ ! -e "$4" ] && [ "$SECONDS" -lt 60 ]; do sleep 0.02; done
[ -e "$4" ] || exit 8
fm_lock_release "$2"
''', '_', LIB, str(lock), str(ready), str(release)], env=env, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    PROCESSES.append(p)
    limit = time.monotonic() + 10
    while not ready.exists() and time.monotonic() < limit and p.poll() is None:
        time.sleep(0.02)
    assert ready.exists(), f'holder failed: {p.communicate()}'
    log('Real holder acquired ' + str(lock) + ': ' + ready.read_text().strip())
    return p, release

def release_holder(pair):
    p, release = pair
    release.touch()
    out, err = p.communicate(timeout=10)
    log(f'holder released exit={p.returncode} stdout={out!r} stderr={err!r}')
    assert p.returncode == 0

def drain(env):
    return run([BASH, 'bin/fm-wake-drain.sh'], env)

def seed_queue(env, key):
    p = shell('''. "$1"; fm_wake_append check "$2" "lock validation notification"''', env, key)
    assert p.returncode == 0

def verify_ack(env, home, p):
    assert p.returncode == 0
    m = re.search(r'--ack-through (\d+) --recovery-generation ([A-Za-z0-9._-]+)', p.stderr)
    assert m, 'missing acknowledgement command'
    ack = run([BASH, 'bin/fm-wake-drain.sh', '--ack-through', m[1], '--recovery-generation', m[2]], env)
    assert ack.returncode == 0
    q = home / 'state/.wake-queue'
    assert not q.exists() or q.read_text() == ''
    log('Persisted queue empty only after explicit acknowledgement.')

try:
    log('Running real production drain and lock interfaces with native processes; no product function or command is stubbed. Stale identity is injected as an on-disk lock record, as left by PID reuse.')
    home, env = lab('live-owner')
    seed_queue(env, 'live-owner')
    lock = home / 'state/.wake-queue.lock'
    before = (home / 'state/.wake-queue').read_bytes()
    h = holder(lock, env)
    pid = (lock / 'pid').read_text().strip()
    p = drain(env)
    assert p.returncode == 0 and f'queue lock remains held by live pid {pid}' in p.stdout
    assert h[0].poll() is None and (lock / 'pid').read_text().strip() == pid
    assert before == (home / 'state/.wake-queue').read_bytes()
    log('Live owner and queued notification preserved at deadline.')
    release_holder(h)
    p = drain(env)
    assert 'lock validation notification' in p.stdout
    verify_ack(env, home, p)
    RESULTS.append({'name':'live owner protected and drain resumes after release','result':'pass','live':True})

    home, env = lab('reused-pid')
    seed_queue(env, 'reused-pid')
    lock = home / 'state/.wake-queue.lock'
    lock.mkdir()
    decoy = subprocess.Popen(['sleep', '60'], env=env)
    PROCESSES.append(decoy)
    probe = shell('. "$1"; fm_pid_start_time "$2"', env, decoy.pid)
    assert probe.returncode == 0 and probe.stdout.strip()
    (lock / 'pid').write_text(str(decoy.pid) + '\n')
    (lock / 'pid-start').write_text(probe.stdout.strip() + 'X\n')
    log(f'Injected stale start identity for live decoy pid={decoy.pid}; current token={probe.stdout.strip()!r}; stored token={(lock / "pid-start").read_text().strip()!r}')
    h = holder(Path(str(lock) + '.steal'), env)
    before = (home / 'state/.wake-queue').read_bytes()
    p = drain(env)
    assert p.returncode == 1 and 'queue lock could not be acquired safely' in p.stderr
    assert 'held by live pid' not in p.stdout + p.stderr
    assert decoy.poll() is None and h[0].poll() is None
    assert before == (home / 'state/.wake-queue').read_bytes()
    exact = shell('''. "$1"; FM_LOCK_HELD_PID=prior-value; rc=0; fm_lock_acquire_wait_bounded "$2" 1 || rc=$?; printf 'rc=%s held=<%s>\n' "$rc" "$FM_LOCK_HELD_PID"''', env, lock)
    assert exact.returncode == 0 and exact.stdout.strip() == 'rc=1 held=<>'
    assert h[0].poll() is None and decoy.poll() is None
    log('Both real processes remained alive through both completed timeouts; no unrelated holder was reported; persisted notification unchanged.')
    RESULTS.append({'name':'reused PID plus live steal holder times out with return 1 and empty held PID','result':'pass','live':True})
    release_holder(h)
    p = drain(env)
    assert 'lock validation notification' in p.stdout and decoy.poll() is None
    verify_ack(env, home, p)
    assert decoy.poll() is None
    log('Stale lock reclaimed after stealer release; unrelated process still alive.')
    RESULTS.append({'name':'stale PID identity reclaimed and queued notification delivered after stealer releases','result':'pass','live':True})

    for bash in (BASH, '/bin/bash'):
        home, env = lab('handoff-' + ('system' if bash == '/bin/bash' else 'path'))
        lock = home / 'state/handoff.lock'
        h = holder(lock, env)
        out = home / 'handoff.out'
        code = '''. "$1"
rc=0
fm_lock_acquire_wait_bounded "$2" 8 || rc=$?
fm_current_pid own
recorded=$(cat "$2/pid-start" 2>/dev/null)
probed=$(fm_pid_start_time "$own")
owner=$(cat "$2/pid" 2>/dev/null)
printf 'rc=%s caller=%s recorded-owner=%s\nrecorded=<%s>\nprobed=<%s>\n' "$rc" "$own" "$owner" "$recorded" "$probed"
[ "$rc" = 0 ] && [ "$owner" = "$own" ] && [ -n "$recorded" ] && [ "$recorded" = "$probed" ] || exit 9
fm_lock_release "$2"
[ ! -e "$2" ] && [ ! -L "$2" ] || exit 10
'''
        waiting = subprocess.Popen([bash, '-c', code, '_', LIB, str(lock)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        PROCESSES.append(waiting)
        time.sleep(0.6)
        assert waiting.poll() is None, 'acquirer should still be waiting for real owner'
        release_holder(h)
        stdout, stderr = waiting.communicate(timeout=12)
        log(f'$ {bash} -c <bounded acquire, inspect persisted owner/token, release>\nexit={waiting.returncode}\n{stdout}{stderr}')
        assert waiting.returncode == 0
        RESULTS.append({'name':f'bounded waiter hands ownership and matching native start token to caller ({bash})','result':'pass','live':True})
    log('All live assertions passed.')
finally:
    for p in PROCESSES:
        if p.poll() is None:
            p.terminate()
            try:
                p.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.communicate(timeout=5)
    shutil.rmtree(SANDBOX)
    log('All scenario-owned processes stopped and temporary lab homes removed.')
    (EVIDENCE / 'round3-live-lock-validation.log').write_text('\n'.join(TRANSCRIPT) + '\n')
    (EVIDENCE / 'round3-live-lock-results.json').write_text(json.dumps(RESULTS, indent=2) + '\n')
