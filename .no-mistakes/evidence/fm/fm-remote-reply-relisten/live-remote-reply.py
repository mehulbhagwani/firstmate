import hashlib, json, os, pathlib, shlex, shutil, socket, subprocess, tempfile, time, sys
ONLY_NONSCHEMA = "--only-nonschema" in sys.argv

ROOT = pathlib.Path.cwd()
EVIDENCE = pathlib.Path('/Users/mehul/.no-mistakes/evidence/01M78SGHQ162R3KV66V39CWB86')
LAB = pathlib.Path(tempfile.mkdtemp(prefix='.fm-remote-live-', dir=ROOT))
CODE = LAB / 'code'
REMOTE = LAB / 'remote'
LOG = REMOTE / 'state/parent-replies.status'
ATTEMPTS = LAB / 'ssh-attempts'
TRANSCRIPT = open(EVIDENCE / ('real-nonschema.log' if ONLY_NONSCHEMA else 'live-remote-reply.log'), 'w', buffering=1)
SERVER = None
RUNNERS = []
PARENTS = []
BASE_ENV = {k:v for k,v in os.environ.items() if not k.startswith(('FM_', 'HERDR_', 'TASKS_AXI_')) and k not in ('TMUX', 'TMUX_PANE')}
BASE_ENV['TMPDIR'] = str(LAB / 'tmp')
RESULTS = []

def note(message):
    print(message, flush=True)
    TRANSCRIPT.write(message + '\n')

def run(argv, env=None, check=True, timeout=40):
    result = subprocess.run([str(a) for a in argv], env=env or BASE_ENV, capture_output=True, text=True, timeout=timeout)
    note('$ ' + shlex.join(str(a) for a in argv))
    note(f'exit={result.returncode}\nstdout={result.stdout.rstrip()}\nstderr={result.stderr.rstrip()}')
    if check and result.returncode != 0:
        raise AssertionError(f'command failed: {argv[0]}: {result.stderr}')
    return result

def wait_until(predicate, label, timeout=40):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate(): return
        time.sleep(.15)
    raise AssertionError('timed out: ' + label)

def atomic(path, data, mode=0o700):
    temp = path.with_name(path.name + '.new')
    temp.write_text(data)
    temp.chmod(mode)
    temp.replace(path)

def remote_mode(mode):
    path = f'{CODE}/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'
    assignments = ['PATH='+path, 'FM_HOME='+str(REMOTE), 'TMPDIR='+str(LAB/'tmp'),
                   'FM_REMOTE_JOB_STATE_ROOT='+str(LAB/'remote-jobs'), 'FM_REMOTE_JOB_PLATFORM_OVERRIDE=Linux']
    prefix = '#!/bin/bash\n'
    if mode == 'normal':
        for assignment in assignments: prefix += 'export ' + shlex.quote(assignment) + '\n'
        body = 'exec /bin/bash --noprofile --norc -c "$SSH_ORIGINAL_COMMAND"\n'
    elif mode == 'usage2':
        body = 'exec /usr/bin/env -i ' + shlex.join(assignments + [str(CODE/'bin/fm-remote-delta-read.sh')]) + '\n'
    elif mode == 'banner':
        body = 'exec /usr/bin/env -i ' + shlex.join(assignments + ['FM_PROCEVENT_CLAIM_ROOT='+str(LAB/'remote-claims'),str(CODE/'bin/fm-procevent.sh'),'list']) + '\n'
    atomic(LAB/'ssh-command', prefix+body)
    note('SSH forced-command configuration: ' + mode)

def server_start():
    global SERVER
    sshlog = open(EVIDENCE/'live-sshd.log','a')
    SERVER = subprocess.Popen(['/usr/sbin/sshd','-D','-e','-f',str(LAB/'sshd_config')],env=BASE_ENV,stdout=sshlog,stderr=sshlog)
    sshlog.close()
    time.sleep(.3)
    assert SERVER.poll() is None, 'sshd did not start'
    note(f'Real OpenSSH server started on loopback:{PORT}, pid={SERVER.pid}')

def parent(name):
    home = LAB/name
    run([CODE/'bin/fm-lab-home.sh','create',home])
    (home/'data/secondmates.md').write_text(f'- {name} - Live SSH reply validation (host: fm-lab-remote; root: {CODE}; home: {REMOTE}; scope: isolated validation; projects: alpha; added 2026-11-13)\n')
    env = BASE_ENV | {'FM_HOME':str(home),'FM_ROOT_OVERRIDE':str(CODE),
        'FM_PROCEVENT_CLAIM_ROOT':str(LAB/'claims'),'FM_SSH_BIN':str(LAB/'ssh-client'),
        'FM_REMOTE_REPLY_WAIT_SECONDS':'1','FM_PROCEVENT_LAUNCH_FLOOR_SECONDS':'1'}
    PARENTS.append(env)
    return home,env

def attempts():
    return ATTEMPTS.read_text().splitlines() if ATTEMPTS.exists() else []

def claim(name): return LAB/'claims'/f'remote-reply-{name}.claim'
def owner(name):
    try: return claim(name).read_text().splitlines()[1]
    except (FileNotFoundError, IndexError): return None

def start(name,env):
    run([CODE/'bin/fm-procevent-remote-reply.sh','arm',name],env)
    output = open(EVIDENCE/f'{name}-runner.log','w')
    p = subprocess.Popen([str(CODE/'bin/fm-procevent.sh'),'start','remote-reply-'+name],env=env,stdout=output,stderr=output)
    output.close()
    RUNNERS.append(p)
    return p

def no_publication(home):
    assert not list((home/'state/procevent-inbox').glob('*.result')), 'error bytes were captured'
    assert not list((home/'state/remote-replies').glob('*.cursor')), 'cursor advanced on failure'
    assert not list((home/'state/remote-replies').glob('*.caught-up')), 'failure claimed caught-up watermark'
    assert not list((home/'state').glob('*.status')), 'error bytes became status'

def raw_read(name,env,expected):
    digest = hashlib.sha256(b'').hexdigest()
    r = run([CODE/'bin/fm-on.sh',name,'fm-remote-delta-read.sh','state/parent-replies.status','0',digest,'1'],env,check=False)
    assert r.returncode == expected, (expected, r.returncode)
    return r

def source(name,env,expected):
    r = run([CODE/'bin/fm-procevent-remote-reply.sh','source',name],env,check=False)
    assert r.returncode == expected and r.stdout == '', (r.returncode, r.stdout)
    assert not list((LAB/'tmp').glob('fm-remote-reply-source.*')), 'completed source left staging output'

def stop(name,env):
    run([CODE/'bin/fm-procevent-remote-reply.sh','retire',name],env)
    wait_until(lambda: owner(name) is None,'retirement released claim')
    count=len(attempts()); time.sleep(1.3)
    assert len(attempts())==count, 'retired source kept retrying'
    assert not list((LAB/'tmp').glob('fm-remote-reply-source.*')), 'retired source left staging output'
    note('Retirement stopped retries, released ownership, and left no staged output.')

def transient(name,code,recover):
    home,env = parent(name)
    raw_read(name,env,code)
    source(name,env,75)
    no_publication(home)
    before=len(attempts())
    p=start(name,env)
    wait_until(lambda: owner(name) is not None,'listener claim')
    held=owner(name)
    wait_until(lambda: len(attempts()) >= before+3,'three real SSH attempts')
    assert p.poll() is None and owner(name)==held, 'listener ended or changed owner'
    no_publication(home)
    run([CODE/'bin/fm-procevent.sh','list'],env)
    other=run([CODE/'bin/fm-procevent.sh','start','remote-reply-'+name],env)
    assert 'already owned' in other.stdout+other.stderr
    assert owner(name)==held
    note(f'Failure {code}: same owner pid={held}, attempts={attempts()[before:]}; no capture, cursor, status, or caught-up watermark.')
    recover()
    line=f'note: recovered after {name}\n'
    LOG.write_text(line)
    status=home/'state'/f'{name}.status'
    wait_until(lambda: status.exists() and line.strip() in status.read_text(),'reply mirrored after recovery')
    wait_until(lambda: list((home/'state/procevent-inbox').glob('*.handled')),'capture handled')
    cursor=home/'state/remote-replies'/f'{name}.cursor'
    assert f'offset={len(line.encode())}\n' in cursor.read_text()
    assert status.read_text().count(line.strip())==1
    assert LOG.read_text()==line
    assert owner(name)==held and p.poll() is None
    note('Mirrored status:\n'+status.read_text()+'Cursor:\n'+cursor.read_text())
    note('Recovery kept owner pid='+held+'; remote log unchanged; reply ingested exactly once in this run.')
    shutil.copy(cursor,EVIDENCE/f'{name}-cursor.txt')
    shutil.copy(status,EVIDENCE/f'{name}-status.txt')
    run([CODE/'bin/fm-procevent.sh','list'],env)
    stop(name,env)
    RESULTS.append({'name':name,'result':'pass','live':True,'transport_exit':code,'owner_pid':held})
    LOG.write_text('')

def refused(name,raw_code,source_code):
    home,env=parent(name)
    raw_read(name,env,raw_code)
    source(name,env,source_code)
    before=len(attempts())
    p=start(name,env)
    p.wait(timeout=30)
    wait_until(lambda: owner(name) is None,'failed source released claim')
    time.sleep(1.4)
    assert len(attempts())==before+1, 'non-retryable failure relaunched'
    no_publication(home)
    output=run([CODE/'bin/fm-procevent.sh','list'],env).stdout
    assert 'remote-reply-'+name in output, 'registration lost'
    note(f'Refusal: raw exit={raw_code}, adapter exit={source_code}; one attempt, no output capture, claim released, registration retained.')
    stop(name,env)
    RESULTS.append({'name':name,'result':'pass','live':True,'transport_exit':raw_code,'source_exit':source_code})

try:
    (LAB/'tmp').mkdir(); (LAB/'claims').mkdir()
    CODE.mkdir(); shutil.copytree(ROOT/'bin',CODE/'bin'); shutil.copy(ROOT/'AGENTS.md',CODE/'AGENTS.md')
    run(['git','-c','init.defaultBranch=main','init','-q',CODE])
    run(['git','-C',CODE,'add','bin','AGENTS.md'])
    run([CODE/'bin/fm-lab-home.sh','create',REMOTE])
    LOG.write_text('')
    for key in ('host_key','client_key'):
        run(['/usr/bin/ssh-keygen','-q','-t','ed25519','-N','','-f',LAB/key])
    shutil.copy(LAB/'client_key.pub',LAB/'authorized_keys')
    with socket.socket() as s:
        s.bind(('127.0.0.1',0)); PORT=s.getsockname()[1]
    host_public=' '.join((LAB/'host_key.pub').read_text().split()[:2])
    (LAB/'known_hosts').write_text(f'[127.0.0.1]:{PORT} {host_public}\n')
    (LAB/'sshd_config').write_text(f'ListenAddress 127.0.0.1\nPort {PORT}\nHostKey {LAB}/host_key\nPidFile {LAB}/sshd.pid\nAuthorizedKeysFile {LAB}/authorized_keys\nStrictModes no\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nUsePAM no\nLogLevel VERBOSE\nForceCommand {LAB}/ssh-command\n')
    (LAB/'ssh_config').write_text(f'Host fm-lab-remote\n HostName 127.0.0.1\n Port {PORT}\n User {os.environ["USER"]}\n IdentityFile {LAB}/client_key\n IdentitiesOnly yes\n BatchMode yes\n StrictHostKeyChecking yes\n UserKnownHostsFile {LAB}/known_hosts\n GlobalKnownHostsFile /dev/null\n ConnectTimeout 2\n')
    atomic(LAB/'ssh-client', '#!/bin/bash\n'+f'/opt/homebrew/bin/python3 -c \'import time; print(time.time())\' >> {shlex.quote(str(ATTEMPTS))}\n'+f'exec /usr/bin/ssh -F {shlex.quote(str(LAB/"ssh_config"))} "$@"\n')
    remote_mode('normal')
    if not ONLY_NONSCHEMA:
        target=(CODE/'bin/fm-procevent-remote-reply.sh').read_bytes()
        base=subprocess.check_output(['git','show','bf0f34680a7618aa5baf36464fe77530fa79fa23:bin/fm-procevent-remote-reply.sh'],cwd=ROOT)
        (CODE/'bin/fm-procevent-remote-reply.sh').write_bytes(base)
        home,env=parent('before-fix')
        source('before-fix',env,255)
        before=len(attempts()); p=start('before-fix',env); p.wait(timeout=20); time.sleep(1.4)
        assert len(attempts())==before+1 and owner('before-fix') is None
        no_publication(home)
        note('BASELINE REPRODUCED: connection refusal ended the listener after one attempt and released the claim.')
        stop('before-fix',env)
        (CODE/'bin/fm-procevent-remote-reply.sh').write_bytes(target)
        transient('transport255',255,server_start)
        LOG.unlink(); LOG.mkdir()
        def recover_reader():
            LOG.rmdir(); LOG.write_text('')
        transient('reader1',1,recover_reader)
        remote_mode('usage2')
        transient('reader2',2,lambda:remote_mode('normal'))
        entry=CODE/'bin/fm-remote-entrypoint.sh'
        entry.rename(entry.with_suffix('.held'))
        try: refused('missing127',127,127)
        finally: entry.with_suffix('.held').rename(entry)
    else:
        server_start()
    remote_mode('banner')
    refused('nonschema',0,1)
    remote_mode('normal')
    note('ALL LIVE SCENARIOS PASSED')
finally:
    for env in PARENTS:
        try: run([CODE/'bin/fm-procevent.sh','sweep-home'],env,timeout=20)
        except Exception as e: note('cleanup sweep: '+str(e))
    worker=LAB/'remote-jobs/worker.pid'
    if worker.exists():
        try:
            run(['/bin/bash','-c','. "$1/bin/fm-remote-job-lib.sh"; fm_remote_job_stop_worker_tree "$(cat "$2/remote-jobs/worker.pid")"','cleanup',CODE,LAB],timeout=20)
        except Exception as e: note('worker cleanup: '+str(e))
    if SERVER is not None and SERVER.poll() is None:
        SERVER.terminate(); SERVER.wait(timeout=10)
    for p in RUNNERS:
        if p.poll() is None:
            p.terminate(); p.wait(timeout=10)
    (EVIDENCE/('real-nonschema-results.json' if ONLY_NONSCHEMA else 'live-results.json')).write_text(json.dumps(RESULTS,indent=2)+'\n')
    shutil.rmtree(LAB)
    note('Disposable SSH server, worker, listeners, test keys, and lab files removed.')
    TRANSCRIPT.close()
