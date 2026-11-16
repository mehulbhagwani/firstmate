import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time

ROOT = Path.cwd()
EVIDENCE = Path('/Users/mehul/.no-mistakes/evidence/01M7K63E5A7DXSMFECRGEEWMHM')
RESULTS = []

def command(args, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs)

class Session:
    def __init__(self, name, setting, extension=True):
        self.name = name
        self.lab = Path(tempfile.mkdtemp(prefix='.pi-live-', dir=ROOT))
        self.sock = None
        self.fd = None
        self.stream = None
        self.trace = (EVIDENCE / (name + '.transcript.jsonl')).open('w')
        self.raw = EVIDENCE / (name + '.rpc.jsonl')
        self.raw.write_text('')
        self.env = {k:v for k,v in os.environ.items() if not k.startswith('FM_') and k not in ['NO_MISTAKES_GATE','TMUX','TASKS_AXI_FILE','TASKS_AXI_BACKEND'] and not k.startswith('HERDR_')}
        self.env.update(FM_HOME=str(self.lab), PI_TELEMETRY='false', PI_OFFLINE='1')
        if setting is not None:
            self.env['FM_PI_BASH_TIMEOUT_MAX_MS'] = setting
        try:
            command(['bash','bin/fm-lab-home.sh','create',str(self.lab)])
            socket_dir = command(['bash','bin/fm-lab-home.sh','tmux-dir',str(self.lab)]).stdout.strip()
            self.env['TMUX_TMPDIR'] = socket_dir
            self.sock = str(Path(socket_dir) / ('tmux-' + str(os.getuid())) / 'fm-lab')
            Path(self.sock).parent.mkdir(mode=0o700, exist_ok=True)
            fifo = self.lab / 'input.fifo'
            os.mkfifo(fifo)
            self.fd = os.open(fifo, os.O_RDWR)
            args = ['pi','--mode','rpc','--no-session','--no-extensions','--no-skills','--no-prompt-templates','--no-themes','--no-context-files','--no-mcp','--offline','--provider','openai-codex','--model','gpt-6-luna','--thinking','low','--tools','bash','--system-prompt','You are running bounded Bash integration checks. Execute exactly the Bash input the user supplies once. Omit optional timeout when absent in their JSON. Do not inspect files or run any other commands. After the tool returns, state its output briefly. If steering messages arrive, acknowledge their tokens after the pending tool finishes without additional tools.']
            if extension:
                args += ['-e',str(ROOT / '.pi/extensions/fm-primary-turnend-guard.ts')]
            shell = 'exec ' + shlex.join(args) + ' < ' + shlex.quote(str(fifo)) + ' > ' + shlex.quote(str(self.raw)) + ' 2> ' + shlex.quote(str(EVIDENCE / (name + '.stderr.log')))
            self.note('launch', {'command':shlex.join(args),'setting':setting,'extension':extension})
            command(['tmux','-S',self.sock,'new-session','-d','-s','primary','-c',str(ROOT),shell],env=self.env)
            end = time.monotonic() + 15
            while not self.raw.exists() and time.monotonic() < end:
                time.sleep(.05)
            self.stream = self.raw.open()
            self.send({'id':'ready','type':'get_state'})
            self.until(lambda event:event.get('id')=='ready', 30)
            if extension:
                self.note('extension-marker', (self.lab/'state/.pi-turnend-extension-loaded').read_text())
        except BaseException:
            self.close()
            raise

    def note(self, kind, data):
        self.trace.write(json.dumps({'time':time.time(),'kind':kind,'data':data})+'\n')
        self.trace.flush()

    def send(self, record):
        self.note('request',record)
        os.write(self.fd,(json.dumps(record)+'\n').encode())

    def until(self, predicate, seconds, on_event=None):
        deadline = time.monotonic()+seconds
        events=[]
        while time.monotonic()<deadline:
            line=self.stream.readline()
            if not line:
                time.sleep(.025)
                continue
            try: event=json.loads(line)
            except json.JSONDecodeError: continue
            self.note('event',event)
            events.append(event)
            if on_event: on_event(event)
            if predicate(event): return events
        raise TimeoutError(self.name + ' did not produce the expected Pi event')

    def run(self, name, requested, expected, error=False, steering=False):
        self.send({'id':name,'type':'prompt','message':'Run exactly one Bash tool call with this JSON input, then report the output: '+json.dumps(requested)})
        started={}
        elapsed={}
        queued=False
        def observe(event):
            nonlocal queued
            if event.get('type')=='tool_execution_start':
                started[event['toolCallId']]=time.monotonic()
                if steering and not queued:
                    self.send({'id':'steer-one','type':'steer','message':'After the pending tool returns acknowledge STEER_ONE. Do not call any other tools.'})
                    self.send({'id':'steer-two','type':'steer','message':'Also acknowledge STEER_TWO after the pending tool returns. Do not call any other tools.'})
                    queued=True
            if event.get('type')=='tool_execution_end':
                elapsed[event['toolCallId']]=round(time.monotonic()-started.get(event['toolCallId'],time.monotonic()),3)
        events=self.until(lambda event:event.get('type')=='agent_settled',70,observe)
        calls=[e for e in events if e.get('type')=='tool_execution_start']
        ends=[e for e in events if e.get('type')=='tool_execution_end']
        assert len(calls)==len(ends)==1, f'{name}: expected one actual tool call, got {calls}, {ends}'
        observed_args=dict(calls[0]['args'])
        if observed_args.get('timeout') is None: observed_args.pop('timeout',None)
        assert calls[0]['toolName']=='bash' and observed_args==requested, f'{name}: model changed requested arguments: {calls[0]}'
        output='\n'.join(c.get('text','') for c in ends[0]['result']['content'])
        assert expected in output, f'{name}: unexpected output {output}'
        assert ends[0].get('isError',False)==error, f'{name}: unexpected result {ends[0]}'
        if error: assert 'SHOULD_NOT_FINISH' not in output
        if steering:
            replies=' '.join(c.get('text','') for e in events if e.get('type')=='message_end' and e.get('message',{}).get('role')=='assistant' for c in e['message'].get('content',[]) if c.get('type')=='text')
            assert queued and 'STEER_ONE' in replies and 'STEER_TWO' in replies, replies
        result={'name':name,'session':self.name,'requested':requested,'output':output,'toolSeconds':elapsed[ends[0]['toolCallId']],'steeringAcknowledged':steering,'result':'pass'}
        RESULTS.append(result)
        self.note('result',result)
        print(json.dumps(result),flush=True)
        (EVIDENCE/'live-results.json').write_text(json.dumps(RESULTS,indent=2)+'\n')

    def isolation(self):
        state=ROOT/'state'
        made_state=not state.exists()
        state.mkdir(exist_ok=True)
        sentinel=state/'.pi-turnend-extension-loaded'
        made_marker=not sentinel.exists()
        if made_marker: sentinel.write_text('existing-session-marker\n999999999\n')
        ambient_marker=self.lab/'state/.pi-turnend-extension-loaded'
        original=ambient_marker.read_bytes()
        original_stat=ambient_marker.stat()
        before=sentinel.read_bytes()
        test_env=dict(self.env,FM_STATE_OVERRIDE=str(self.lab/'state'))
        try:
            def test_once(index):
                result=subprocess.run(['bash','tests/fm-pi-bash-timeout.test.sh'],env=test_env,text=True,capture_output=True)
                assert result.returncode==0, result.stderr
                return {'run':index,'stdout':result.stdout,'stderr':result.stderr,'exit':result.returncode}
            runs=[test_once(1)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                runs+=list(pool.map(test_once,[2,3]))
            assert sentinel.read_bytes()==before, 'Developer state marker was overwritten'
            assert ambient_marker.read_bytes()==original, 'Running Pi marker was overwritten'
            assert ambient_marker.stat().st_mtime_ns==original_stat.st_mtime_ns, 'Running Pi marker was touched'
            result={'name':'test-state-isolation','result':'pass','runs':runs,'worktreeMarkerUnchanged':True,'runningPiMarkerUnchanged':True,'runningPiMarkerMtimeUnchanged':True,'runningPiMarkerSha256':hashlib.sha256(original).hexdigest()}
            self.note('isolation',result)
            (EVIDENCE/'state-isolation.json').write_text(json.dumps(result,indent=2)+'\n')
            print(json.dumps(result),flush=True)
        finally:
            if made_marker: sentinel.unlink()
            if made_state: state.rmdir()

    def close(self):
        if self.sock:
            if Path(self.sock).exists():
                subprocess.run(['tmux','-S',self.sock,'kill-server'],env=self.env,capture_output=True)
            command(['bash','bin/fm-lab-home.sh','teardown',str(self.lab)])
        if self.fd is not None: os.close(self.fd)
        if self.stream: self.stream.close()
        shutil.rmtree(self.lab)
        self.note('cleanup','Private tmux server stopped; disposable lab home removed')
        self.trace.close()


def drive(name,setting,cases,extension=True,isolation=False):
    session=Session(name,setting,extension)
    try:
        if isolation: session.isolation()
        for case in cases: session.run(*case)
    finally: session.close()

if __name__=='__main__':
    drive('cap-1000','1000',[
        ('omitted-and-steering',{'command':'printf START; sleep 3; printf SHOULD_NOT_FINISH'},'Command timed out after 1 seconds',True,True),
        ('larger-explicit',{'command':'sleep 3; printf SHOULD_NOT_FINISH','timeout':60},'Command timed out after 1 seconds',True),
        ('shorter-explicit',{'command':'sleep 1; printf SHOULD_NOT_FINISH','timeout':0.2},'Command timed out after 0.2 seconds',True),
        ('equal-explicit',{'command':'sleep 2; printf SHOULD_NOT_FINISH','timeout':1},'Command timed out after 1 seconds',True),
        ('quick-command',{'command':'printf QUICK_WORKS'},'QUICK_WORKS'),
    ],isolation=True)
    drive('cap-500','500',[
        ('subsecond',{'command':'sleep 2; printf SHOULD_NOT_FINISH'},'Command timed out after 0.5 seconds',True),
    ])
    drive('cap-1','1',[
        ('minimum',{'command':'sleep 1; printf SHOULD_NOT_FINISH'},'Command timed out after 0.001 seconds',True),
    ])
    drive('cap-maximum','2147483647',[
        ('maximum-omitted',{'command':'printf MAXIMUM_WORKS'},'MAXIMUM_WORKS'),
        ('maximum-explicit',{'command':'printf MAXIMUM_CLAMPS','timeout':2147483.648},'MAXIMUM_CLAMPS'),
    ])
    drive('cap-oversized','2147483648',[
        ('oversized-setting',{'command':'printf OVERSIZED_IGNORED'},'OVERSIZED_IGNORED'),
        ('oversized-preserves-explicit',{'command':'sleep 1; printf SHOULD_NOT_FINISH','timeout':0.2},'Command timed out after 0.2 seconds',True),
    ])
    drive('cap-invalid','01',[
        ('leading-zero-ignored',{'command':'sleep 1.2; printf INVALID_IGNORED'},'INVALID_IGNORED'),
    ])
    drive('cap-unset',None,[
        ('unset-default',{'command':'sleep 1.2; printf DEFAULT_WORKS'},'DEFAULT_WORKS'),
        ('unset-explicit',{'command':'sleep 1; printf SHOULD_NOT_FINISH','timeout':0.2},'Command timed out after 0.2 seconds',True),
    ])
    drive('without-extension','500',[
        ('worker-unaffected',{'command':'sleep 1.2; printf WORKER_WORKS'},'WORKER_WORKS'),
    ],extension=False)
