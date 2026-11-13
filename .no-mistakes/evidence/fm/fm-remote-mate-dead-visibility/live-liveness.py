import os, pathlib, subprocess, tempfile, time, json, re, shutil
ROOT = pathlib.Path.cwd()
EVIDENCE = pathlib.Path('/Users/mehul/.no-mistakes/evidence/01M7A36HCSM6FJF09SQX85QWDY')
log = (EVIDENCE / 'live-liveness-transcript.log').open('w', buffering=1)
def note(s):
    print(s, flush=True); log.write(s + '\n')
env = os.environ.copy()
for k in list(env):
    if k.startswith(('FM_', 'HERDR_', 'TASKS_AXI_')) or k in ('NO_MISTAKES_GATE','TMUX','REX_SESSION','REX_BLOCK','TERM_PROGRAM'):
        env.pop(k, None)
lab = pathlib.Path(tempfile.mkdtemp(prefix='fm-lab.',dir=ROOT))
watch = None
socket = None
results = []
def run(args, timeout=30, check=True, extra=None):
    r = subprocess.run([str(a) for a in args], cwd=ROOT, env=env | (extra or {}), text=True, capture_output=True, timeout=timeout)
    if check and r.returncode:
        raise RuntimeError(f'{args}: rc={r.returncode}\n{r.stdout}\n{r.stderr}')
    return r

def tmux(*args, **kw):
    return run(['tmux','-S',socket,*args], **kw)

def meta(id, target=None, remote=False):
    target = target or 'firstmate:fm-' + id
    text = f'window={target}\nkind=secondmate\nharness=codex\nbackend=tmux\n'
    if remote:
        text += f'remote_host=fm-lab-no-such-host.invalid\nremote_backend=herdr\nremote_herdr_session=fm-lab-unreachable\nremote_target=fm-lab-unreachable:w1:p1\nhome={lab}/remote-home\n'
    (lab/'state'/f'{id}.meta').write_text(text)

def contents(name):
    p = lab/'state'/name
    return p.read_text() if p.exists() else ''

def probe(target):
    return run(['bash','-c','. bin/fm-backend.sh; fm_backend_agent_state tmux "$1"','bash',target], timeout=30).stdout

def start(tag, threshold='3'):
    global watch
    out=(EVIDENCE/f'{tag}.out').open('w'); err=(EVIDENCE/f'{tag}.err').open('w')
    watch=subprocess.Popen([str(ROOT/'bin/fm-watch.sh')],cwd=ROOT,env=env|{'FM_SECONDMATE_LIVENESS_UNCERTAIN_TICKS':threshold},stdout=out,stderr=err)
    out.close(); err.close()
    note(f'RUN bin/fm-watch.sh [{tag}] with real tmux, FM_POLL=1, FM_SECONDMATE_LIVENESS_SECS=1, threshold={threshold}')

def stop():
    global watch
    if watch and watch.poll() is None:
        watch.terminate(); watch.wait(timeout=20)
    watch=None

def until(pred, label, timeout=65):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if pred(): return
        time.sleep(.15)
    raise AssertionError('Timed out: '+label)

def alert_end(tag):
    until(lambda: watch.poll() is not None, tag+' alert')
    out=(EVIDENCE/f'{tag}.out').read_text(); err=(EVIDENCE/f'{tag}.err').read_text()
    note('PRODUCT STDOUT: '+out.strip())
    if err: note('PRODUCT STDERR: '+err.strip())
    assert watch.returncode == 0, (watch.returncode, out, err)
    assert 'liveness remains' in out, out
    return out

def drain(tag, ack=True, seq=None):
    r=run(['bin/fm-wake-drain.sh'],check=False)
    (EVIDENCE/f'{tag}-drain.log').write_text(r.stdout+r.stderr)
    note('PRODUCT DRAIN: '+r.stdout.strip())
    m=re.search(r'WAKE_ACK_REQUIRED:.*--ack-through (\d+).*--recovery-generation ([A-Za-z0-9._-]+)',r.stderr)
    if ack and m:
        run(['bin/fm-wake-drain.sh','--ack-through',seq or m[1],'--recovery-generation',m[2]])
    return r

def record(name):
    results.append({'name':name,'result':'pass','live':True})
    note('SCENARIO PASS: '+name)

try:
    run(['bin/fm-lab-home.sh','create',lab])
    sockdir=run(['bin/fm-lab-home.sh','tmux-dir',lab]).stdout.strip()
    socket=f'{sockdir}/tmux-{os.getuid()}/fm-lab'
    pathlib.Path(socket).parent.mkdir(mode=0o700, exist_ok=True)
    env.update(FM_HOME=str(lab),FM_BACKEND='tmux',TMUX_TMPDIR=sockdir,FM_POLL='1',FM_SIGNAL_GRACE='0',FM_CHECK_INTERVAL='999999',FM_HEARTBEAT='999999',FM_SECONDMATE_LIVENESS_SECS='1')
    (lab/'config/backend').write_text('tmux\n')
    (lab/'config/supervision-host-off').touch()
    tmux('new-session','-d','-s','firstmate','-n','fm-ops','-c',ROOT,'-e',f'FM_HOME={lab}','sleep 600')
    env['TMUX']=f'{socket},{tmux("display-message","-p","#{pid}").stdout.strip()},0'
    tmux('set-option','-g','automatic-rename','off')
    meta('ops')
    before=tmux('list-panes','-a','-F','#{pane_id}\t#{pane_pid}\t#{pane_current_command}').stdout
    note('REAL ENDPOINT BEFORE: '+before.strip())
    note('REAL CLASSIFIER: '+probe('firstmate:fm-ops'))
    assert probe('firstmate:fm-ops')=='ambiguous'
    start('ambiguous-first')
    out=alert_end('ambiguous-first'); assert 'after 3 consecutive probes' in out
    assert before==tmux('list-panes','-a','-F','#{pane_id}\t#{pane_pid}\t#{pane_current_command}').stdout
    assert not contents('.secondmate-relaunch-ops')
    note('DURABLE QUEUE: '+contents('.wake-queue').strip())
    record('Persistent ambiguous real endpoint alerts at three probes without replacing the process')
    drain('first')
    count=int(contents('.secondmate-uncertain-episode-ops').split()[1])
    start('ambiguous-repeat')
    until(lambda:int(contents('.secondmate-uncertain-episode-ops').split()[1])>=count+3,'repeat probes')
    assert watch.poll() is None
    assert not contents('.wake-queue')
    note('Same endpoint preserved; repeated probes='+contents('.secondmate-uncertain-episode-ops').strip()+'; notification queue remains empty')
    stop(); drain('repeat')
    record('Restarting monitoring does not repeat an alert during the same uncertain episode')

    # Run an installed, real CLI without submitting any agent work. No mock process names.
    tmux('respawn-pane','-k','-t','firstmate:fm-ops','-c',ROOT,'codex')
    until(lambda:probe('firstmate:fm-ops')=='alive','actual Codex process alive',30)
    note('REAL CLI PANE: '+tmux('capture-pane','-p','-t','firstmate:fm-ops').stdout.strip())
    start('alive-clears')
    until(lambda:not contents('.secondmate-uncertain-episode-ops'),'alive clears episode')
    assert not contents('.secondmate-uncertain-alert-ops')
    assert watch.poll() is None
    stop(); drain('alive')
    note('Real Codex endpoint classified alive; episode and alert cleared; no liveness alert emitted')
    record('A real live agent clears the previous episode and rearms notification')

    # A malformed recorded target is a real classifier input failure; no probe shim.
    meta('ops','firstmate:fm-ops:invalid')
    assert probe('firstmate:fm-ops:invalid')=='unreadable'
    start('unreadable-first')
    out=alert_end('unreadable-first'); assert 'remains unreadable after 3' in out
    drain('unreadable-unacked',False)
    oldrows=contents('.wake-queue').splitlines()
    old=next(row.split('\t') for row in oldrows if 'secondmate-liveness-uncertain-ops-' in row)
    assert tmux('list-panes','-a','-F','#{pane_current_command}').stdout.strip() != 'sleep'
    record('An unreadable recorded endpoint alerts without changing the running agent')

    meta('ops')
    start('new-episode')
    until(lambda:not contents('.secondmate-uncertain-episode-ops'),'recovery while first row unacknowledged')
    tmux('respawn-pane','-k','-t','firstmate:fm-ops','-c',ROOT,'sleep 600')
    alert_end('new-episode')
    rows=[r.split('\t') for r in contents('.wake-queue').splitlines() if 'secondmate-liveness-uncertain-ops-' in r]
    assert len(rows)==2 and rows[0][3]!=rows[1][3], rows
    note('TWO DISTINCT EPISODES: '+json.dumps(rows))
    drain('new-episode',seq=old[1])
    assert old[3] not in contents('.wake-queue') and rows[1][3] in contents('.wake-queue')
    note('AFTER ACK OF OLD EPISODE: '+contents('.wake-queue').strip())
    drain('remaining')
    record('Acknowledging an older alert preserves the new episode notification')

    # Preserve a previously alerted episode across genuine SSH transport failure.
    previous=contents('.secondmate-uncertain-episode-ops')
    meta('ops',remote=True)
    (lab/'data/secondmates.md').write_text(f'- ops - Lab remote (host: fm-lab-no-such-host.invalid; root: {ROOT}; home: {lab}/remote-home; scope: lab; projects: none; added 2026-11-13)\n')
    route_before=(lab/'state/ops.meta').read_bytes()
    registry_before=(lab/'data/secondmates.md').read_bytes()
    r=run(['bin/fm-on.sh','ops','fm-remote-secondmate-control.sh','state','ops'],check=False)
    note('REAL SSH FAILURE rc='+str(r.returncode)+': '+r.stderr.strip()); assert r.returncode==255
    start('unavailable')
    until(lambda:contents('.watch-triage.log').count('remote host unavailable')>=4,'four unavailable probes')
    assert watch.poll() is None and not contents('.wake-queue')
    assert previous==contents('.secondmate-uncertain-episode-ops')
    assert route_before==(lab/'state/ops.meta').read_bytes() and registry_before==(lab/'data/secondmates.md').read_bytes()
    assert not contents('.secondmate-relaunch-ops')
    note('PRODUCT TRIAGE: '+'\n'.join(s for s in contents('.watch-triage.log').splitlines() if 'remote host unavailable' in s))
    stop(); drain('unavailable')
    record('Repeated real SSH transport failures stay silent and preserve the existing episode and remote route')

    (lab/'data/secondmates.md').unlink()
    meta('ops')
    tmux('respawn-pane','-k','-t','firstmate:fm-ops','-c',ROOT,'codex')
    until(lambda:probe('firstmate:fm-ops')=='alive','healthy ops',30)
    tmux('new-window','-d','-t','firstmate','-n','fm-alert-ops','-c',ROOT,'sleep 600')
    meta('alert-ops')
    stable=tmux('list-panes','-a','-F','#{pane_id}\t#{pane_pid}\t#{pane_current_command}').stdout
    start('prefixed-ids')
    out=alert_end('prefixed-ids'); assert 'secondmate alert-ops' in out and 'after 3' in out
    assert not contents('.secondmate-uncertain-episode-ops')
    assert contents('.secondmate-uncertain-alert-alert-ops')
    after=tmux('list-panes','-a','-F','#{pane_id}\t#{pane_pid}\t#{pane_current_command}').stdout
    note('PANE SNAPSHOTS: '+repr(stable)+' -> '+repr(after))
    assert [x.split('\t')[:2] for x in stable.splitlines()]==[x.split('\t')[:2] for x in after.splitlines()]
    assert not contents('.secondmate-relaunch-ops') and not contents('.secondmate-relaunch-alert-ops')
    drain('prefixed')
    record('A healthy ops agent cannot clear alert-ops uncertainty or prevent its alert')
    note('ALL LIVE SCENARIOS PASSED')
except Exception as exc:
    note('ERROR: '+repr(exc)); raise
finally:
    stop()
    if socket:
        tmux('kill-server',check=False)
        run(['bin/fm-lab-home.sh','teardown',lab],check=False)
    shutil.rmtree(lab)
    (EVIDENCE/'live-results.json').write_text(json.dumps(results,indent=2)+'\n')
    note('Removed disposable lab and stopped its private tmux server.')
    log.close()
