import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time

ROOT = Path.cwd()
EVIDENCE = Path('/Users/mehul/.no-mistakes/evidence/01M7B8029NKQ2HK3A62ZFRMTGF')
BASE = '427056c4181c41074ad24f051f79919330df0fa5'
LAB = Path(tempfile.mkdtemp(prefix='.fm-lock-live.', dir=ROOT))
LIB = ROOT / 'bin/fm-wake-lib.sh'
DRAIN = ROOT / 'bin/fm-wake-drain.sh'
children = []
results = []
log = (EVIDENCE / 'live-lock-transcript.txt').open('w')

def note(text):
    print(text, flush=True)
    log.write(text + '\n')
    log.flush()

def environment(home):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith('FM_') and not k.startswith('HERDR_')
           and k not in ('STATE', 'CONFIG', 'DATA', 'TASKS_AXI_FILE', 'TASKS_AXI_BACKEND')}
    env.update(FM_HOME=str(home), FM_STATUS_PRESENTATION_LOCK_TIMEOUT='1')
    return env

def run(args, home, timeout=15):
    return subprocess.run([str(a) for a in args], env=environment(home),
                          cwd=ROOT, capture_output=True, text=True, timeout=timeout)

def shell(code, home, *args, lib=LIB):
    return run(['bash', '-c', '. "$1"; ' + code, '_', lib, *args], home)

def make_home(name):
    home = LAB / name
    r = run(['bash', ROOT / 'bin/fm-lab-home.sh', 'create', home], home)
    assert r.returncode == 0, r.stderr
    r = shell('fm_wake_append check lock-validation "notification retained until acknowledgement"', home)
    assert r.returncode == 0, r.stderr
    return home

def holder(home, lock):
    p = subprocess.Popen(['bash', '-c',
        '. "$1"; fm_lock_try_acquire "$2" || exit 10; '
        'trap \'fm_lock_release "$2"\' EXIT; '
        'printf "ready pid=%s token=%s\\n" "$(cat "$2/pid")" "$(cat "$2/pid-start")"; '
        'IFS= read -r release', '_', str(LIB), str(lock)], env=environment(home),
        cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True)
    children.append(p)
    ready = p.stdout.readline().strip()
    assert ready.startswith('ready pid='), (ready, p.poll())
    note(ready)
    assert int((lock / 'pid').read_text()) == p.pid
    token = shell('fm_pid_start_time "$2"', home, p.pid).stdout.strip()
    assert (lock / 'pid-start').read_text().strip() == token
    assert token and token == token.strip()
    return p

def release(p):
    if p.poll() is None:
        out, err = p.communicate('release\n', timeout=8)
        assert p.returncode == 0, (out, err)

def drain(home):
    start = time.monotonic()
    r = run(['bash', DRAIN], home)
    elapsed = time.monotonic() - start
    note(f'$ FM_HOME=<isolated lab> FM_STATUS_PRESENTATION_LOCK_TIMEOUT=1 bash bin/fm-wake-drain.sh\nexit={r.returncode} elapsed={elapsed:.3f}s')
    note('stdout:\n' + r.stdout + 'stderr:\n' + r.stderr)
    assert elapsed < 12, elapsed
    return r

def recover_and_ack(home):
    r = drain(home)
    assert r.returncode == 0 and 'notification retained until acknowledgement' in r.stdout, r
    assert 'SKIPPED' not in r.stdout
    match = re.search(r'--ack-through (\d+) --recovery-generation ([A-Za-z0-9._-]+)', r.stderr)
    assert match, r.stderr
    queue = home / 'state/.wake-queue'
    note('persisted queue before acknowledgement: ' + queue.read_text().strip())
    a = run(['bash', DRAIN, '--ack-through', match[1], '--recovery-generation', match[2]], home)
    assert a.returncode == 0, a.stderr
    assert queue.read_text() == ''
    note('acknowledgement exit=0; persisted queue is empty; notification consumed exactly once')

def scenario(name, fn):
    note('\nSCENARIO: ' + name)
    try:
        fn()
    except Exception as e:
        results.append(dict(name=name, result='fail', live=True, detail=repr(e)))
        raise
    else:
        results.append(dict(name=name, result='pass', live=True))
        note('RESULT: pass')

def contention():
    home = make_home('matching-owner')
    lock = home / 'state/.wake-queue.lock'
    p = holder(home, lock)
    before = (home / 'state/.wake-queue').read_bytes()
    r = drain(home)
    assert r.returncode == 0 and f'held by live pid {p.pid}' in r.stdout
    assert (home / 'state/.wake-queue').read_bytes() == before
    assert p.poll() is None and int((lock / 'pid').read_text()) == p.pid
    note('matching owner is still alive; its PID/start token and queued notification are unchanged')
    release(p)
    recover_and_ack(home)

def reused(which):
    home = make_home('reused-' + which)
    lock = home / ('state/.wake-queue.lock' if which == 'queue' else 'state/.status-presentation-lock')
    p = holder(home, lock)
    old_token = shell('fm_pid_start_time 1', home).stdout.strip()
    assert old_token and old_token != (lock / 'pid-start').read_text().strip()
    (lock / 'pid-start').write_text(old_token + '\n')
    stealer = holder(home, Path(str(lock) + '.steal'))
    note(f'persisted PID reuse condition: pid={p.pid}; recorded prior start={old_token}; actual live start=' + shell('fm_pid_start_time "$2"', home, p.pid).stdout.strip())
    before = (home / 'state/.wake-queue').read_bytes()
    r = drain(home)
    assert f'{which if which == "queue" else "status presentation"} lock could not be acquired safely' in r.stderr
    assert 'held by live pid' not in r.stdout
    assert r.returncode == (1 if which == 'queue' else 0)
    assert p.poll() is None and stealer.poll() is None
    assert (home / 'state/.wake-queue').read_bytes() == before
    assert (lock / 'pid-start').read_text().strip() == old_token
    note('both unrelated live process and recovery-mutex owner survived; queue retained; no false live-holder advisory')
    if which == 'queue':
        direct = shell('FM_LOCK_HELD_PID=sentinel; rc=0; fm_lock_acquire_wait_bounded "$2" 1 || rc=$?; printf "rc=%s held=<%s>\\n" "$rc" "${FM_LOCK_HELD_PID:-}"', home, lock)
        note('direct executable contract: ' + direct.stdout.strip())
        assert direct.stdout.strip() == 'rc=1 held=<>'
        oldbin = LAB / 'baseline/bin'
        oldbin.mkdir(parents=True)
        (oldbin / 'fm-wake-lib.sh').write_bytes(subprocess.check_output(['git', 'show', BASE + ':bin/fm-wake-lib.sh'], cwd=ROOT))
        for dep in ['fm-path-lib.sh', 'fm-timeout-lib.sh']:
            (oldbin / dep).symlink_to(ROOT / 'bin' / dep)
        old = shell('rc=0; fm_lock_acquire_wait_bounded "$2" 1 || rc=$?; printf "rc=%s held=<%s>\\n" "$rc" "${FM_LOCK_HELD_PID:-}"', home, lock, lib=oldbin / 'fm-wake-lib.sh')
        note('pre-change executable counterfactual: ' + old.stdout.strip())
        assert old.stdout.strip() == f'rc=124 held=<{p.pid}>'
    release(stealer)
    recover_and_ack(home)
    assert p.poll() is None
    note('stale-lock recovery did not signal the unrelated live process')
    release(p)

def waiting_drain():
    home = make_home('wait-release')
    lock = home / 'state/.wake-queue.lock'
    p = holder(home, lock)
    env = environment(home)
    env['FM_STATUS_PRESENTATION_LOCK_TIMEOUT'] = '5'
    d = subprocess.Popen(['bash', str(DRAIN)], env=env, cwd=ROOT, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, start_new_session=True)
    children.append(d)
    time.sleep(0.35)
    assert d.poll() is None and int((lock / 'pid').read_text()) == p.pid
    release(p)
    out, err = d.communicate(timeout=12)
    note('$ bash bin/fm-wake-drain.sh (5s budget; genuine owner releases while drain waits)\nexit=' + str(d.returncode) + '\nstdout:\n' + out + 'stderr:\n' + err)
    assert d.returncode == 0 and 'notification retained until acknowledgement' in out and 'SKIPPED' not in out
    recover_and_ack(home)

def stale_directories():
    for shape in ('top-level', 'nested'):
        home = make_home('stale-directory-' + shape)
        dead = subprocess.Popen(['sleep', '30'], start_new_session=True)
        children.append(dead)
        token = shell('fm_pid_start_time "$2"', home, dead.pid).stdout.strip()
        dead.terminate()
        dead.wait(timeout=5)
        lock = home / 'state/.wake-queue.lock'
        for path in (lock, Path(str(lock) + '.steal')):
            path.mkdir()
            owner = path / (path.name + '.owner.previous') if shape == 'nested' else path
            owner.mkdir(exist_ok=True)
            (owner / 'pid').write_text(str(dead.pid) + '\n')
            (owner / 'pid-start').write_text(token + '\n')
            os.utime(owner, (1, 1))
            os.utime(path, (1, 1))
        note(f'recovery input: {shape} real directories for queue and steal mutex; former pid={dead.pid} confirmed exited')
        recover_and_ack(home)
        leftovers = list((home / 'state').glob('.wake-queue.lock*'))
        assert leftovers == [], leftovers
        note('no queue lock, nested directory, or staged-owner residue remains')

try:
    note('Runtime: ' + subprocess.check_output(['uname', '-s'], text=True).strip())
    note('Target: ' + subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip())
    note('Real bash/ps and product CLI, isolated marked homes, no backend/CLI stubs. PID reuse is seeded as an older real start token beside a currently live PID; kernel PID recycling is not forced.')
    scenario('Genuine live owner is reported accurately, preserves the notification, and releases for normal acknowledgement', contention)
    scenario('Reused queue PID under a live recovery mutex refuses without blaming the unrelated process, then recovers', lambda: reused('queue'))
    scenario('Reused presentation PID refuses without false live-holder text and preserves queued work', lambda: reused('presentation'))
    scenario('A waiting notification drain resumes after a genuine owner releases', waiting_drain)
    scenario('Stale real-directory queue and recovery locks are reclaimed in top-level and nested forms', stale_directories)
finally:
    for p in reversed(children):
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait(timeout=3)
    shutil.rmtree(LAB)
    note('\nCleanup: all owned processes stopped and isolated homes removed')
    (EVIDENCE / 'live-lock-results.json').write_text(json.dumps(results, indent=2) + '\n')
    log.close()
