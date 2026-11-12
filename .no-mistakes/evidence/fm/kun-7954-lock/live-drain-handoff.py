import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

root=Path.cwd()
evidence=Path('/Users/mehul/.no-mistakes/evidence/01M78H3P9H4KQ49C0BCY980QK2')
lib=str(root/'bin/fm-wake-lib.sh')
home=Path(tempfile.mkdtemp(prefix='.fm-drain-handoff-',dir=root))
env={k:v for k,v in os.environ.items() if not k.startswith('FM_') and k not in ('STATE','CONFIG','DATA','PROJECTS','TASKS_AXI_FILE','TASKS_AXI_BACKEND')}
log=[]
processes=[]
def emit(s):
    print(s,flush=True)
    log.append(s)
try:
    subprocess.run(['bash','bin/fm-lab-home.sh','create',str(home)],env=env,check=True,capture_output=True)
    env.update(FM_HOME=str(home),FM_STATUS_PRESENTATION_LOCK_TIMEOUT='8')
    for index,bash in enumerate(('bash','/bin/bash')):
        subprocess.run([bash,'-c','. "$1"; fm_wake_append check handoff "notification after waiting"','_',lib],env=env,check=True)
        ready=home/f'ready-{index}'
        release=home/f'release-{index}'
        holder=subprocess.Popen([bash,'-c','''. "$1"; fm_lock_try_acquire "$STATE/.wake-queue.lock" || exit 7
printf ready > "$2"
while [ ! -e "$3" ] && [ "$SECONDS" -lt 45 ]; do sleep 0.02; done
[ -e "$3" ] || exit 8
fm_lock_release "$STATE/.wake-queue.lock"''','_',lib,str(ready),str(release)],env=env)
        processes.append(holder)
        deadline=time.monotonic()+10
        while not ready.exists() and time.monotonic()<deadline:
            time.sleep(.02)
        assert ready.exists()
        start=time.monotonic()
        drain=subprocess.Popen([bash,'bin/fm-wake-drain.sh'],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        processes.append(drain)
        time.sleep(.6)
        assert drain.poll() is None and holder.poll() is None
        release.touch()
        holder.wait(timeout=10)
        assert holder.returncode==0
        stdout,stderr=drain.communicate(timeout=15)
        emit(f'$ {bash} bin/fm-wake-drain.sh\nReal holder released after drain had waited 0.6s.\nexit={drain.returncode} elapsed={time.monotonic()-start:.3f}s\nstdout:\n{stdout}stderr:\n{stderr}')
        assert drain.returncode==0 and 'notification after waiting' in stdout and 'SKIPPED' not in stdout
        assert not (home/'state/.wake-queue.lock').exists()
        emit('Timed helper handed the lock to the running drain; notification delivered and lock released.')
finally:
    for p in processes:
        if p.poll() is None:
            p.terminate()
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill();p.wait(timeout=5)
    shutil.rmtree(home)
    emit('All scenario-owned processes stopped and temporary home removed.')
    (evidence/'live-drain-handoff.log').write_text('\n'.join(log)+'\n')
