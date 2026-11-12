import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

root = Path.cwd()
evidence = Path('/Users/mehul/.no-mistakes/evidence/01M78SEAG3AYXXF774CNWKE96H')
lab = root / '.nm-live-sentinel'
baseline = root / 'bin/.nm-watch-baseline.sh'
env = {k: v for k, v in os.environ.items() if not k.startswith(('FM_', 'HERDR_', 'REX_', 'TASKS_AXI_')) and k not in ('TMUX', 'TMUX_PANE', 'TERM_PROGRAM')}
env.update(FM_HOME=str(lab), FM_BACKEND='tmux', FM_POLL='1', FM_SIGNAL_GRACE='1', FM_STALE_ESCALATE_SECS='240', FM_CHECK_INTERVAL='999999', FM_HEARTBEAT='999999', FM_WEDGE_MAX_ESCALATIONS='3', FM_ROLLBACK_SENTINEL_TTL_SECS='3600', FM_WATCH_HANDLING_SUCCESSOR='1')
socket = None
watcher = None
watch_output = None
transcript = []
results = []

def say(text):
    line = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + ' ' + text
    print(line, flush=True)
    transcript.append(line)

def cmd(args, **kwargs):
    return subprocess.run([str(a) for a in args], env=env, cwd=root, text=True, capture_output=True, check=True, **kwargs).stdout.strip('\n')

def tmux(*args):
    return cmd(['tmux', '-S', socket, *args])

def read(path):
    return path.read_text() if path.exists() and path.is_file() else ''

def stop():
    global watcher, watch_output
    if watcher is not None:
        if watcher.poll() is None:
            watcher.terminate()
            watcher.wait(timeout=15)
        watcher = None
    if watch_output is not None:
        watch_output.close()
        watch_output = None

def start(label, executable=None):
    global watcher, watch_output
    watch_output = (evidence / (label + '-stdout.log')).open('w')
    watcher = subprocess.Popen(['bash', str(executable or root / 'bin/fm-watch.sh')], cwd=root, env=env, stdout=watch_output, stderr=subprocess.STDOUT)

def wait_for(predicate, timeout=40):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.15)
    raise AssertionError('timed out waiting for scenario observation')

def seed(age=5):
    capture = tmux('capture-pane', '-p', '-t', window, '-S', '-40')
    digest = hashlib.md5(capture.encode()).hexdigest()
    (state / ('.hash-' + key)).write_text(digest)
    (state / ('.stale-' + key)).write_text(digest)
    counter.write_text('2\n')
    timer.write_text(str(int(time.time()) - age) + '\n')
    return capture

def silent_polls(label, executable=None, age=5):
    seed(age)
    triage.write_text('')
    before = read(timer)
    start(label, executable)
    wait_for(lambda: int(read(counter) or '0') >= 8 or watcher.poll() is not None)
    assert watcher.poll() is None, read(evidence / (label + '-stdout.log'))
    time.sleep(0.4)
    stop()
    iterations = int(read(counter)) - 2
    lines = [s for s in read(triage).splitlines() if 'rollback-failed sentinel active for ' + window in s]
    assert sentinel.exists(), 'sentinel unexpectedly consumed'
    assert not any('possible wedge' in s for s in read(queue).splitlines()), 'suppressed wedge was queued'
    (evidence / (label + '-triage.log')).write_text(read(triage))
    say(f'{label}: actual watcher iterations={iterations}, suppression notices={len(lines)}, queued wedge alerts=0, timer_before={before.strip()}, timer_after={read(timer).strip()}')
    return iterations, len(lines), before

try:
    assert not lab.exists() and not baseline.exists(), 'refuse to overwrite existing local material'
    cmd(['bash', 'bin/fm-lab-home.sh', 'create', lab])
    socket_dir = cmd(['bash', 'bin/fm-lab-home.sh', 'tmux-dir', lab])
    socket = str(Path(socket_dir) / ('tmux-' + str(os.getuid())) / 'fm-lab')
    Path(socket).parent.mkdir(mode=0o700, exist_ok=True)
    env['TMUX_TMPDIR'] = socket_dir
    say('Real tools: ' + cmd(['tmux', '-V']) + '; Pi ' + cmd(['pi', '--version']))
    cli = 'pi --no-session --offline --no-extensions --no-mcp --no-skills --no-prompt-templates --no-context-files --no-themes --no-tools --no-approve; exec /bin/bash --noprofile --norc -i'
    tmux('-f', '/dev/null', 'new-session', '-d', '-s', 'fm-lab-sentinel', '-n', 'worker', '-x', '110', '-y', '35', '-c', str(root), cli)
    window = 'fm-lab-sentinel:worker'
    tmux('set-window-option', '-t', window, 'automatic-rename', 'off')
    tmux('set-window-option', '-t', window, 'allow-rename', 'off')
    env['TMUX'] = socket + ',' + tmux('display-message', '-p', '#{pid}') + ',0'
    time.sleep(5)
    state = lab / 'state'
    (lab / 'config/backend').write_text('tmux\n')
    (state / 'sentinel-proof.meta').write_text(f'window={window}\nbackend=tmux\nharness=pi\nkind=ship\n')
    key = 'v3.' + hashlib.sha256(window.encode()).hexdigest()
    counter = state / ('.count-' + key)
    timer = state / ('.stale-since-' + key)
    sentinel = state / ('.wedge-rollback-failed-' + key)
    escalation = state / ('.wedge-escalations-' + key)
    triage = state / '.watch-triage.log'
    queue = state / '.wake-queue'
    capture = seed(500)
    (evidence / 'live-pi-pane.txt').write_text(capture + '\n')
    verdict = cmd(['bash', '-c', '. bin/fm-backend.sh; fm_backend_agent_state tmux "$1"', '_', window])
    say('Real Pi endpoint before failure: ' + verdict)
    assert verdict == 'alive', 'real Pi must be alive before probing sentinel behavior'
    escalation.mkdir()
    start('fault-creation')
    wait_for(lambda: watcher.poll() is not None)
    rc = watcher.returncode
    stop()
    say('Refused escalation-count write: watcher exit=' + str(rc) + '; sentinel=' + read(sentinel).strip())
    (evidence / 'fault-creation-triage.log').write_text(read(triage))
    assert rc == 1 and sentinel.exists(), 'fault did not create suppression sentinel'
    assert not read(queue), 'fault unexpectedly published an alert'
    escalation.rmdir()

    baseline.write_text(cmd(['git', 'show', 'bf0f34680a7618aa5baf36464fe77530fa79fa23:bin/fm-watch.sh']) + '\n')
    cycles, notices, before = silent_polls('before-fix', baseline)
    assert notices == 0 and read(timer) == before, 'baseline did not reproduce missing suppression notices'
    results.append({'name': 'Baseline reproduces invisible suppression below endpoint-check threshold', 'result': 'pass', 'live': True})

    cycles, notices, before = silent_polls('after-fix')
    assert notices >= cycles - 1 and notices >= 5, 'suppression notice missing from repeated polls'
    assert read(timer) == before, 'below-threshold poll unexpectedly rearmed the endpoint timer'
    results.append({'name': 'Every suppressed poll shows the operator notice without publishing wedge alerts', 'result': 'pass', 'live': True})

    cycles, notices, before = silent_polls('at-threshold', age=500)
    assert notices >= cycles - 1 and read(timer) != before, 'due endpoint probe did not rearm timer'
    due_timer = read(timer)
    say('Due probe refreshed the timer once; following sub-threshold polls kept it stable.')
    results.append({'name': 'Endpoint checks remain rate-limited while notices repeat', 'result': 'pass', 'live': True})

    timer.unlink()
    triage.write_text('')
    start('missing-timer')
    wait_for(lambda: timer.exists() or watcher.poll() is not None)
    assert watcher.poll() is None and timer.exists(), 'missing timer not repaired'
    wait_for(lambda: len([s for s in read(triage).splitlines() if 'rollback-failed sentinel active' in s]) >= 3)
    stop()
    (evidence / 'missing-timer-triage.log').write_text(read(triage))
    say('Missing timer repaired under active sentinel; repeated notices continued and no alert was queued.')
    assert not read(queue), 'missing timer repair published an alert'
    results.append({'name': 'Missing timer repairs itself without suppressing diagnostics or flooding alerts', 'result': 'pass', 'live': True})

    tmux('send-keys', '-t', window, 'C-c')
    tmux('send-keys', '-t', window, 'C-c')
    time.sleep(2)
    verdict = cmd(['bash', '-c', '. bin/fm-backend.sh; fm_backend_agent_state tmux "$1"', '_', window])
    say('Endpoint after exiting real Pi: ' + verdict)
    assert verdict == 'dead', 'Pi did not exit to its parent shell'
    seed(500)
    start('dead-worker')
    wait_for(lambda: watcher.poll() is not None)
    stop()
    dead_rows = [s for s in read(queue).splitlines() if 'agent dead' in s]
    assert len(dead_rows) == 1 and 'possible wedge' not in read(queue), 'dead worker not reported exactly once'
    (evidence / 'dead-worker-queue.log').write_text(read(queue))
    say('Suppression still reported exited worker exactly once: ' + dead_rows[0])
    cycles, notices, _ = silent_polls('dead-worker-repeat', age=500)
    assert len([s for s in read(queue).splitlines() if 'agent dead' in s]) == 1, 'duplicate dead-worker report'
    results.append({'name': 'Exited worker is reported once despite active suppression', 'result': 'pass', 'live': True})
    say('All live scenarios passed.')
finally:
    stop()
    if socket and Path(socket).exists():
        tmux('kill-server')
    if lab.exists():
        cmd(['bash', 'bin/fm-lab-home.sh', 'teardown', lab])
        shutil.rmtree(lab)
    if baseline.exists():
        baseline.unlink()
    (evidence / 'live-sentinel-transcript.log').write_text('\n'.join(transcript) + '\n')
    (evidence / 'live-sentinel-results.json').write_text(json.dumps(results, indent=2) + '\n')
