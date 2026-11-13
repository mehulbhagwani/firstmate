import json, os, pathlib, shlex, shutil, subprocess, tempfile, time
ROOT = pathlib.Path.cwd()
EVID = pathlib.Path('/Users/mehul/.no-mistakes/evidence/01M7APM9ZKBB32Q5HZ862S47V5')
records = []
report = EVID / 'pi-timeout-verified-transcript.txt'
report.write_text('Real Pi 1.5.2 CLI, private tmux socket, stock Bash tool, tracked Firstmate extension.\nCommands use harmless sleeps rather than scanning private files. No model or tool mocks.\n\n')
def log(text):
    print(text, flush=True)
    with report.open('a') as f: f.write(text+'\n')
def run(args, **kw):
    return subprocess.run(list(map(str,args)), check=True, capture_output=True, text=True, **kw).stdout.strip()
class Pi:
    def __init__(self, label, setting):
        self.label = label
        self.lab = pathlib.Path(tempfile.mkdtemp(prefix='.pi-timeout-lab-', dir=ROOT))
        run(['bin/fm-lab-home.sh','create',self.lab])
        self.socketdir = run(['bin/fm-lab-home.sh','tmux-dir',self.lab])
        self.env = dict(os.environ)
        for key in list(self.env):
            if key.startswith(('FM_', 'HERDR_')) or key in ['NO_MISTAKES_GATE','TMUX','TMUX_PANE','TASKS_AXI_FILE','TASKS_AXI_BACKEND','REX_SESSION','REX_BLOCK']:
                self.env.pop(key)
        self.env.update(FM_HOME=str(self.lab), TMUX_TMPDIR=self.socketdir, PI_OFFLINE='1', PI_TELEMETRY='0')
        if setting is not None: self.env['FM_PI_BASH_TIMEOUT_MAX_MS']=setting
        self.out = EVID / (label + '-verified-rpc.jsonl')
        self.err = EVID / (label + '-verified-stderr.txt')
        self.out.write_text(''); self.err.write_text('')
        args = ['pi','--mode','rpc','--no-session','--approve','--offline','--no-extensions','-e',str(ROOT/'.pi/extensions/fm-primary-turnend-guard.ts'),'--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-mcp','--tools','bash','--model','openai-codex/gpt-6.1-sol','--thinking','low','--system-prompt','You are performing a bounded live shell-tool experiment in an isolated lab. Execute only the exact bash arguments requested, once. Do not retry failed commands. Never inspect credentials or change files. After the result, briefly report it. Honor queued user steering messages.']
        command = 'stty -echo; exec '+shlex.join(args)+' > '+shlex.quote(str(self.out))+' 2> '+shlex.quote(str(self.err))
        self.tmux('new-session','-d','-s','primary','-c',ROOT,'-e','FM_HOME='+str(self.lab),command)
        self.cursor = 0
        self.send({'id':'ready','type':'get_state'})
        self.wait(lambda e:e.get('id')=='ready',30)
        log(f'Launched {label}: FM_PI_BASH_TIMEOUT_MAX_MS={setting!r}; real Pi RPC ready.')
    def tmux(self,*args): return run(['tmux','-L','fm-lab',*args],env=self.env)
    def send(self,msg):
        self.tmux('send-keys','-t','primary','-l',json.dumps(msg))
        self.tmux('send-keys','-t','primary','Enter')
    def read(self):
        lines=self.out.read_text().splitlines()
        data=[]
        for line in lines[self.cursor:]:
            try: data.append(json.loads(line))
            except json.JSONDecodeError: break
            self.cursor+=1
        return data
    def wait(self,pred,seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            for e in self.read():
                if pred(e): return e
            time.sleep(.05)
        raise RuntimeError('RPC deadline; stderr='+self.err.read_text()[-1500:])
    def case(self,name,sleep,timeout,expected,steering=False):
        command=f"printf 'START_{name}\\n'; sleep {sleep}; printf 'COMPLETE_{name}\\n'"
        args={'command':command}
        if timeout is not None: args['timeout']=timeout
        msg='Call the bash tool exactly once with this exact JSON input: '+json.dumps(args)+'. Do not add or change any argument, especially timeout. If the provider schema requires a null for an absent optional timeout, use null. Do not use any other tool or retry. Then report the actual tool outcome.'
        self.read()
        log('\nCASE '+name+'\nRequested tool arguments: '+json.dumps(args))
        self.send({'id':name,'type':'prompt','message':msg})
        events=[]; start=None; end=None; queued=False
        deadline=time.monotonic()+100
        while time.monotonic()<deadline:
            for e in self.read():
                events.append(e)
                if e.get('type')=='tool_execution_start':
                    start=e; log('Pi tool start: '+json.dumps(e))
                if e.get('type')=='tool_execution_update' and steering and not queued:
                    text=json.dumps(e.get('partialResult',{}))
                    if 'START_'+name in text:
                        queued=True
                        self.send({'id':name+'-steer1','type':'steer','message':'After the current shell ends, say STEERING_ONE_ACK. Do not retry or run more commands.'})
                        self.send({'id':name+'-steer2','type':'steer','message':'Also say STEERING_TWO_ACK when you can respond. Do not retry or run more commands.'})
                        log('Sent two steering messages while the shell was still running.')
                if e.get('type')=='queue_update' and e.get('steering'): log('Pi queued steering: '+json.dumps(e))
                if e.get('type')=='tool_execution_end': end=e; log('Pi tool result: '+json.dumps(e))
                if e.get('type')=='agent_settled':
                    if not start or not end: raise RuntimeError('No real bash execution: '+json.dumps(events)[-3000:])
                    output='\n'.join(c.get('text','') for c in end['result'].get('content',[]))
                    duration=end.get('durationMs',-1)/1000
                    assistants=[e['message'] for e in events if e.get('type')=='message_end' and e.get('message',{}).get('role')=='assistant']
                    answer='\n'.join(c.get('text','') for m in assistants for c in m.get('content',[]) if c.get('type')=='text')
                    log('Pi response: '+answer)
                    errs=[]
                    normalized=json.loads(run(['node',EVID/'pi-normalize-bash.mjs',json.dumps(start.get('args'))]))
                    if normalized!=args: errs.append('model did not execute requested input after native Pi normalization')
                    if expected is None:
                        if end.get('isError') or 'COMPLETE_'+name not in output: errs.append('uncapped command did not complete')
                        if duration<sleep-.2: errs.append('uncapped duration too short')
                    else:
                        if not end.get('isError') or 'timed out' not in output.lower() or 'COMPLETE_'+name in output: errs.append('expected timeout did not stop shell')
                        if not expected-.2<=duration<=expected+2: errs.append('incorrect timeout duration '+str(duration))
                    if steering:
                        if not queued or not any(e.get('type')=='queue_update' and len(e.get('steering',[]))>=2 for e in events): errs.append('two steering messages were not observed queued')
                        if 'STEERING_ONE_ACK' not in answer or 'STEERING_TWO_ACK' not in answer: errs.append('queued steering was not acknowledged')
                    result={'name':name,'setting':self.env.get('FM_PI_BASH_TIMEOUT_MAX_MS'),'requested':args,'durationSeconds':duration,'result':'fail' if errs else 'pass','errors':errs,'rpc':self.out.name}
                    records.append(result)
                    (EVID/'pi-timeout-verified-results.json').write_text(json.dumps(records,indent=2)+'\n')
                    log('Observed result: '+json.dumps(result))
                    return
            time.sleep(.03)
        raise RuntimeError('Scenario exceeded live test deadline')
    def close(self):
        try:
            self.tmux('capture-pane','-p','-t','primary','-S','-100')
            self.tmux('kill-server')
        finally:
            run(['bin/fm-lab-home.sh','teardown',self.lab])
            shutil.rmtree(self.lab)
            log('Removed isolated '+self.label+' session and lab.')
groups=[
 ('default-off',None,[('uncapped-omitted',6,None,None,False)]),
 ('cap-5000ms','5000',[('omitted-queued-steering',12,None,5,True),('explicit-60-seconds',12,60,5,False),('shorter-timeout',2,.25,.25,False),('equal-timeout',8,5,5,False)]),
 ('cap-500ms','500',[('fractional-omitted',2,None,.5,False),('fractional-explicit',2,1,.5,False),('fractional-shorter',2,.25,.25,False)]),
 ('invalid-setting','invalid',[('invalid-unchanged',1,None,None,False)])]
for label,setting,cases in groups:
    p=None
    try:
        p=Pi(label,setting)
        for case in cases:
            if case[0] in ['uncapped-omitted','omitted-queued-steering','fractional-omitted','invalid-unchanged']: p.case(*case)
    finally:
        if p:p.close()
log('\nLive cases completed: '+str(len(records)))
if any(r['result']=='fail' for r in records): raise SystemExit(1)
