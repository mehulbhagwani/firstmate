import os, pathlib, subprocess, tempfile, time, signal, hashlib, re, json, shutil
ROOT = pathlib.Path.cwd()
EVIDENCE = pathlib.Path('/Users/mehul/.no-mistakes/evidence/01M7B88AVW9XJ2GHN1A5MBXR2Z')
LAB = pathlib.Path(tempfile.mkdtemp(prefix='.sentinel-lab-', dir=ROOT))
ENV = {k:v for k,v in os.environ.items() if not k.startswith(('FM_', 'HERDR_', 'REX_', 'TASKS_AXI_')) and k not in ('TMUX','TERM_PROGRAM')}
ENV.update(FM_HOME=str(LAB), FM_BACKEND='tmux', FM_POLL='1', FM_SIGNAL_GRACE='1', FM_CHECK_INTERVAL='999999', FM_HEARTBEAT='999999', FM_WEDGE_MAX_ESCALATIONS='2', FM_STALE_ESCALATE_SECS='240', FM_ROLLBACK_SENTINEL_TTL_SECS='3600', PI_TELEMETRY='0')
SOCKET = None
WATCH = None
BASE = ROOT / 'bin/.fm-watch-before-live-test.sh'
REPORT = []
TRANSCRIPT = EVIDENCE / 'sentinel-live-transcript.log'
TRANSCRIPT.write_text('')
def say(s):
    print(s, flush=True)
    with TRANSCRIPT.open('a') as f: f.write(s+'\n')
def run(args, **kw):
    return subprocess.run([str(a) for a in args], cwd=ROOT, env=ENV, text=True, capture_output=True, timeout=kw.pop('timeout',40), check=kw.pop('check',True), **kw)
def sh(code, *args):
    return run(['bash','-c',code,'_',*args]).stdout.strip()
def tmux(*args, **kw):
    return run(['tmux','-S',SOCKET,*args], **kw)
def content(path):
    return path.read_text() if path.exists() else ''
def stop():
    global WATCH
    if WATCH is not None:
        if WATCH.poll() is None:
            WATCH.send_signal(signal.SIGTERM)
            try: WATCH.wait(timeout=15)
            except subprocess.TimeoutExpired:
                WATCH.kill(); WATCH.wait()
        WATCH = None

def arm(label, watcher='bin/fm-watch.sh', expected_polls=5, age=5, ttl=3600, cap=2, sentinel=True, expect_wake=False, count_fault=False):
    global WATCH
    # These are the public persisted watcher records: seed the prior suppression
    # episode, but run the actual full CLI and actual tmux/Pi processes unchanged.
    pane=tmux('capture-pane','-p','-t',WINDOW,'-S','-40').stdout.rstrip('\n')
    digest=hashlib.md5(pane.encode()).hexdigest()
    (STATE / ('.hash-'+KEY)).write_text(digest)
    (STATE / ('.stale-'+KEY)).write_text(digest)
    (STATE / ('.count-'+KEY)).write_text('2\n')
    timer=STATE / ('.stale-since-'+KEY)
    if age is None: timer.unlink(missing_ok=True)
    else: timer.write_text(str(int(time.time())-age)+'\n')
    counter=STATE / ('.wedge-escalations-'+KEY)
    if count_fault:
        counter.write_text('0\n')
        counter.chmod(0o444)
    if sentinel: SENTINEL.write_text(str(int(time.time()))+' rollback-failed\n')
    else: SENTINEL.unlink(missing_ok=True)
    (STATE / '.watch-triage.log').write_text('')
    env=ENV.copy()
    env.update(FM_WATCH_HANDLING_SUCCESSOR='1', FM_WEDGE_MAX_ESCALATIONS=str(cap), FM_ROLLBACK_SENTINEL_TTL_SECS=str(ttl), PS4='+${SECONDS} ${FUNCNAME[0]:-main}:${LINENO}: ')
    trace=LAB / (label+'.trace')
    output=EVIDENCE / (label+'-watcher.txt')
    with trace.open('w') as tf, output.open('w') as out:
        WATCH=subprocess.Popen(['bash','-x',str(ROOT / watcher)],cwd=ROOT,env=env,stdout=out,stderr=tf,text=True)
        deadline=time.monotonic()+65
        while time.monotonic()<deadline:
            tr=content(trace)
            calls=len(re.findall(r'^\++\d+ [^\n]*: wedge_timer_check ',tr,re.M))
            if WATCH.poll() is not None: break
            if not expect_wake and calls>=expected_polls:
                time.sleep(.35)
                break
            time.sleep(.2)
        rc=WATCH.poll()
        stop()
    if count_fault: counter.chmod(0o644)
    tr=content(trace)
    interesting=[s for s in tr.splitlines() if re.search(r': (wedge_timer_check |wedge_dead_record |fm_backend_agent_state tmux|triage_log .*rollback-failed)',s)]
    (EVIDENCE / (label+'-executed-calls.log')).write_text('\n'.join(interesting)+'\n')
    logs=content(STATE / '.watch-triage.log')
    (EVIDENCE / (label+'-triage.log')).write_text(logs)
    queue=content(STATE / '.wake-queue')
    (EVIDENCE / (label+'-queue.txt')).write_text(queue)
    calls=len(re.findall(r'^\++\d+ [^\n]*: wedge_timer_check ',tr,re.M))
    probes=len(re.findall(r'^\++\d+ [^\n]*: wedge_dead_record ',tr,re.M))
    lines=sum('rollback-failed sentinel active for '+WINDOW in s for s in logs.splitlines())
    record=dict(label=label, polls=calls, probes=probes, suppression_lines=lines, wedge_notifications=queue.count('possible wedge'), death_notifications=queue.count('agent dead'), sentinel_exists=SENTINEL.exists(), watcher_exit=rc, output=content(output))
    REPORT.append(record)
    say(json.dumps(record))
    if logs: say(logs.strip())
    if queue: say('Persisted notification queue:\n'+queue.strip())
    return record

try:
    run(['bin/fm-lab-home.sh','create',LAB])
    socketdir=run(['bin/fm-lab-home.sh','tmux-dir',LAB]).stdout.strip()
    SOCKET=str(pathlib.Path(socketdir)/('tmux-'+str(os.getuid()))/'fm-lab')
    pathlib.Path(SOCKET).parent.mkdir(mode=0o700,exist_ok=True)
    ENV['TMUX_TMPDIR']=socketdir
    ENV['PI_CODING_AGENT_DIR']=str(LAB/'pi-config')
    # No model prompt is submitted. This uses the real installed Pi executable
    # at its idle composer, the actual nonterminal-stale watcher population.
    tmux('-f','/dev/null','new-session','-d','-s','fm-lab-sentinel','-n','worker','-x','120','-y','36','-c',str(ROOT),'-e','FM_HOME='+str(LAB),'-e','PI_CODING_AGENT_DIR='+str(LAB/'pi-config'),'-e','PI_TELEMETRY=0','pi --offline --no-approve --no-session --no-extensions --no-mcp --no-skills --no-context-files --no-prompt-templates --no-themes --tui-mode regular')
    WINDOW='fm-lab-sentinel:worker'
    tmux('set-window-option','-t',WINDOW,'automatic-rename','off')
    tmux('set-window-option','-t',WINDOW,'allow-rename','off')
    ENV['TMUX']=SOCKET+',0,0'
    STATE=LAB/'state'
    (STATE/'sentinel-worker.meta').write_text('window='+WINDOW+'\nbackend=tmux\nharness=pi\nkind=ship\n')
    (STATE/'sentinel-worker.status').write_text('working: live sentinel diagnostic scenario\n')
    sh('. "$1"; fm_wake_status_mark_current "$2" "$3"',ROOT/'bin/fm-wake-lib.sh',STATE,STATE/'sentinel-worker.status')
    KEY=sh('. "$1"; window_key "$2"',ROOT/'bin/fm-watch-key-lib.sh',WINDOW)
    SENTINEL=STATE/('.wedge-rollback-failed-'+KEY)
    time.sleep(4)
    pane=tmux('capture-pane','-p','-t',WINDOW,'-S','-40').stdout
    (EVIDENCE/'pi-live-pane.txt').write_text(pane)
    verdict=sh('. "$1"; fm_backend_agent_state tmux "$2"',ROOT/'bin/fm-backend.sh',WINDOW)
    say('Real Pi endpoint classification before scenarios: '+verdict)
    say('Live pane:\n'+pane.strip())
    assert verdict=='alive', verdict
    BASE.write_text(run(['git','show','427056c4181c41074ad24f051f79919330df0fa5:bin/fm-watch.sh']).stdout)
    fault=arm('storage-write-failure',age=500,sentinel=False,expect_wake=True,count_fault=True)
    assert fault['watcher_exit']==1 and fault['sentinel_exists'] and fault['wedge_notifications']==0, fault
    a=arm('before-below-threshold',str(BASE.relative_to(ROOT)))
    assert a['polls']>=5 and a['suppression_lines']==0 and a['probes']==0 and a['wedge_notifications']==0, a
    b=arm('after-below-threshold')
    assert b['polls']>=5 and b['suppression_lines']==b['polls'] and b['probes']==0 and b['wedge_notifications']==0, b
    c=arm('after-probe-due',age=500)
    assert c['polls']>=5 and c['suppression_lines']==c['polls'] and c['probes']==1 and c['wedge_notifications']==0, c
    missing=arm('after-missing-timer',age=None)
    assert missing['polls']>=5 and missing['suppression_lines']==missing['polls'] and missing['probes']==1 and missing['wedge_notifications']==0, missing
    d=arm('after-operator-recovery',age=500,sentinel=False,expect_wake=True)
    assert d['wedge_notifications']==1 and d['suppression_lines']==0, d
    # Keep the real running monitor and tmux adapter for the death boundary.
    # Replacing only the lab's Pi with a real shell removes the agent process.
    # Clear the earlier delivered notification through the production drain.
    drain=run(['bin/fm-wake-drain.sh'])
    ack=re.search(r'--ack-through (\d+) --recovery-generation ([A-Za-z0-9._-]+)',drain.stderr)
    if ack: run(['bin/fm-wake-drain.sh','--ack-through',ack[1],'--recovery-generation',ack[2]])
    tmux('respawn-pane','-k','-t',WINDOW,'/bin/bash --noprofile --norc')
    time.sleep(1)
    verdict=sh('. "$1"; fm_backend_agent_state tmux "$2"',ROOT/'bin/fm-backend.sh',WINDOW)
    say('Real endpoint classification after stopping lab Pi: '+verdict)
    assert verdict=='dead', verdict
    e=arm('after-agent-exit',age=500,expect_wake=True)
    assert e['death_notifications']==1 and e['wedge_notifications']==0 and e['suppression_lines']==1, e
    f=arm('after-agent-exit-repeat',age=500)
    assert f['death_notifications']==1 and f['wedge_notifications']==0 and f['polls']>=5 and f['suppression_lines']==f['polls'] and f['probes']==1, f
    say('PASS: reproduced missing diagnostics on the base, then verified per-poll diagnostics, bounded real endpoint probes, no wedge flood, operator recovery, and one-time agent-death notification on the target.')
finally:
    stop()
    if SOCKET and pathlib.Path(SOCKET).exists(): tmux('kill-server',check=False)
    run(['bin/fm-lab-home.sh','teardown',LAB],check=False)
    shutil.rmtree(LAB)
    BASE.unlink(missing_ok=True)
    (EVIDENCE/'sentinel-live-results.json').write_text(json.dumps(REPORT,indent=2)+'\n')
    say('Cleanup: lab monitor stopped, private tmux server stopped, disposable home and temporary baseline script removed.')
