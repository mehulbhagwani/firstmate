import os, sys, json, time, shlex, subprocess, tempfile, pathlib, shutil
ROOT=pathlib.Path.cwd()
EVIDENCE=pathlib.Path('/Users/mehul/.no-mistakes/evidence/01M7B6EEDS5Y9FD8BQFR9QDJ38')
LABEL=sys.argv[1]
SETTING=None if sys.argv[2]=='unset' else sys.argv[2]
EXTENSION=sys.argv[3]!='no-extension'
EXTENSION_PATH=ROOT/'.pi/extensions/fm-primary-turnend-guard.ts' if sys.argv[3]=='extension' else ROOT/sys.argv[3]
CASES=json.loads(sys.argv[4])
lab=pathlib.Path(tempfile.mkdtemp(prefix='.fm-pi-timeout-',dir=ROOT))
env=os.environ.copy()
for k in list(env):
    if k.startswith(('FM_', 'HERDR_')) or k in ('NO_MISTAKES_GATE','TMUX','TMUX_PANE','TASKS_AXI_FILE','TASKS_AXI_BACKEND'):
        env.pop(k,None)
env['FM_HOME']=str(lab)
env['PI_OFFLINE']='1'
env['PI_TELEMETRY']='0'
if SETTING is not None: env['FM_PI_BASH_TIMEOUT_MAX_MS']=SETTING
out=EVIDENCE/(LABEL+'.jsonl')
err=EVIDENCE/(LABEL+'.stderr.log')
log=EVIDENCE/(LABEL+'.transcript.jsonl')
socket=None
records=[]
def record(kind,data):
    entry={'observedAt':time.time(),'kind':kind,'data':data}
    records.append(entry)
    with log.open('a') as f: f.write(json.dumps(entry)+'\n')
def tmux(*args,check=True):
    return subprocess.run(['tmux','-S',socket,*args],env=env,text=True,capture_output=True,check=check)
def send(message):
    record('request',message)
    tmux('send-keys','-t','primary','-l',json.dumps(message))
    tmux('send-keys','-t','primary','Enter')
position=0
buffer=''
def events():
    global position,buffer
    if not out.exists(): return []
    with out.open() as f:
        f.seek(position); buffer+=f.read(); position=f.tell()
    lines=buffer.split('\n'); buffer=lines.pop()
    result=[]
    for line in lines:
        if not line.strip(): continue
        try: event=json.loads(line)
        except json.JSONDecodeError: record('non-json-output',line); continue
        result.append(event)
        if event.get('type') not in ('message_update','tool_execution_update'): record('event',event)
    return result
try:
    subprocess.run(['bin/fm-lab-home.sh','create',str(lab)],check=True,capture_output=True,text=True)
    socket_dir=subprocess.check_output(['bin/fm-lab-home.sh','tmux-dir',str(lab)],text=True).strip()
    env['TMUX_TMPDIR']=socket_dir
    socket=f'{socket_dir}/tmux-{os.getuid()}/fm-lab'
    pathlib.Path(socket).parent.mkdir(mode=0o700)
    cmd=['pi','--mode','rpc','--no-session','--offline','--approve','--no-context-files','--no-extensions','--no-skills','--no-prompt-templates','--no-mcp','--tools','bash','--model','openai-codex/gpt-6.1-sol','--thinking','low','--system-prompt','You are executing a bounded shell-tool integration check. Execute only the exact bash tool input requested, once. Do not inspect files, run other commands, modify files, or retry a timeout. Treat a timeout as expected test data. After the tool result, briefly report it and stop. Obey later steering messages.']
    if EXTENSION: cmd+=['-e',str(EXTENSION_PATH)]
    shellcmd='exec '+shlex.join(cmd)+' > '+shlex.quote(str(out))+' 2> '+shlex.quote(str(err))
    record('launch',{'setting':SETTING,'extension':EXTENSION,'command':shlex.join(cmd),'piVersion':subprocess.check_output(['pi','--version'],text=True).strip()})
    tmux('new-session','-d','-s','primary','-c',str(ROOT),'-e','FM_HOME='+str(lab),shellcmd)
    time.sleep(1)
    send({'id':'ready','type':'get_state'})
    ready=False
    deadline=time.monotonic()+35
    while time.monotonic()<deadline and not ready:
        for event in events():
            if event.get('id')=='ready' and event.get('success'): ready=True
        time.sleep(.1)
    if not ready: raise RuntimeError('Pi RPC did not become ready: '+err.read_text())
    for n,case in enumerate(CASES):
        label=case['name']; started=time.monotonic(); seen=[]; steered=False
        requested=case['input']
        prompt='Invoke bash exactly once with this JSON input, preserving whether the timeout field is absent: '+json.dumps(requested)+'. Do not retry. Then report the result.'
        send({'id':label,'type':'prompt','message':prompt})
        deadline=time.monotonic()+90
        settled=False
        while time.monotonic()<deadline and not settled:
            for event in events():
                seen.append(event)
                if case.get('steering') and event.get('type')=='tool_execution_start' and not steered:
                    time.sleep(.2)
                    send({'id':'steer-a','type':'steer','message':'After the running command returns, acknowledge STEERING_ONE. Do not retry or run other commands.'})
                    send({'id':'steer-b','type':'steer','message':'Also acknowledge STEERING_TWO. Do not retry or run other commands.'})
                    steered=True
                if event.get('type')=='agent_settled': settled=True
            time.sleep(.05)
        executions=[e for e in seen if e.get('type') in ('tool_execution_start','tool_execution_end')]
        result={'name':label,'requested':requested,'elapsedSeconds':round(time.monotonic()-started,3),'settled':settled,'executions':executions,'steeringSent':steered}
        record('case-result',result)
        print(json.dumps(result),flush=True)
        if not settled: raise RuntimeError('Pi did not settle within 90 seconds')
    record('extension-marker', (lab/'state/.pi-turnend-extension-loaded').read_text() if (lab/'state/.pi-turnend-extension-loaded').exists() else None)
finally:
    if socket and pathlib.Path(socket).exists(): tmux('kill-server',check=False)
    if (lab/'.fm-lab-home').exists(): subprocess.run(['bin/fm-lab-home.sh','teardown',str(lab)],check=True,capture_output=True,text=True)
    shutil.rmtree(lab)
    record('cleanup','Private tmux server stopped and disposable home removed')
