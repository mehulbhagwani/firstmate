import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

root = Path.cwd()
evidence = Path('/Users/mehul/.no-mistakes/evidence/01M78H3P9H4KQ49C0BCY980QK2')
home = Path(tempfile.mkdtemp(prefix='.fm-lock-takeover-', dir=root))
env = {k:v for k,v in os.environ.items() if not k.startswith('FM_') and k not in ('STATE','CONFIG','DATA','PROJECTS','TMUX','TMUX_PANE','TASKS_AXI_FILE','TASKS_AXI_BACKEND')}
logs = []
processes = []
handles = []

def log(s):
    print(s, flush=True)
    logs.append(s)

def wait_for(predicate, timeout, message):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.02)
    raise RuntimeError(message)

def read(path):
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return ''

try:
    p = subprocess.run(['bash','bin/fm-lab-home.sh','create',str(home)],env=env,text=True,capture_output=True,check=True)
    log('$ bash bin/fm-lab-home.sh create <disposable home>\n' + p.stdout)
    state = home / 'state'
    (home / 'config/backend').write_text('tmux\n')
    # All backend lookups, if any, address this nonexistent lab-only socket.
    # No actual fleet endpoints or command replacements are used.
    env.update(FM_HOME=str(home), FM_PROC_ROOT_OVERRIDE=str(home/'no-proc'), TZ='America/Los_Angeles', FM_GUARD_GRACE='1', FM_POLL='1', FM_SIGNAL_GRACE='1', FM_CHECK_INTERVAL='999999', FM_HEARTBEAT='999999', TMUX=str(home/'private-tmux-socket')+',0,0')
    for name in ('old',):
        handle = (home / (name+'.log')).open('w')
        handles.append(handle)
        old = subprocess.Popen(['bash','bin/fm-watch.sh'],cwd=root,env=env,stdout=handle,stderr=subprocess.STDOUT)
        processes.append(old)
    lock = state / '.watch.lock'
    wait_for(lambda: read(lock/'pid')==str(old.pid) and bool(read(lock/'pid-identity')),10,'old watcher never acquired lock')
    current = read(lock/'pid-identity')
    ps_env = dict(env,LC_ALL='C',COLUMNS='10000')
    legacy = subprocess.check_output(['ps','-p',str(old.pid),'-o','lstart=','-o','command='],env=ps_env,text=True).strip()
    assert legacy and legacy != current
    log(f'Native old watcher pid={old.pid}\ncurrent identity={current}\nlegacy local-time identity={legacy}')
    (lock/'pid-start').unlink(missing_ok=True)
    (lock/'pid-identity').write_text(legacy+'\n')
    for _ in range(100):
        os.kill(old.pid,signal.SIGSTOP)
        held = any(read(p/'pid')==str(old.pid) for p in state.iterdir() if p.name != '.watch.lock' and (p.name.endswith('.lock') or p.name.endswith('.lock.steal')))
        if not held:
            break
        os.kill(old.pid,signal.SIGCONT)
        time.sleep(0.05)
    else:
        raise RuntimeError('could not pause old watcher outside other locks')
    original_stat=state.stat()
    handle=(home/'new.log').open('w')
    handles.append(handle)
    new = subprocess.Popen(['bash','bin/fm-watch.sh'],cwd=root,env=env,stdout=handle,stderr=subprocess.STDOUT)
    processes.append(new)
    new.wait(timeout=25)
    assert new.returncode == 0
    assert 'check: ' in read(home/'new.log')
    assert not (lock/'pid').exists()
    log(f'Successor exit={new.returncode}; recovery output:\n{read(home/"new.log")}\nSuccessor released its lock before old watcher resumes.')
    os.kill(old.pid,signal.SIGCONT)
    old.wait(timeout=10)
    old_output=read(home/'old.log')
    after_stat=state.stat()
    same=(original_stat.st_dev,original_stat.st_ino)==(after_stat.st_dev,after_stat.st_ino)
    log(f'Old watcher exit={old.returncode}; output:\n{old_output}\nstate_directory_exists={state.is_dir()}\nsame_state_device_and_inode={same}')
    assert same
    assert old.returncode == 1 and 'state directory was torn down' in old_output
    log('FAIL: replaced watcher should stand down with exit 0; reproduced exit 1 against real product without mock tools.')
finally:
    for p in processes:
        if p.poll() is None:
            p.send_signal(signal.SIGCONT)
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=5)
    for h in handles:
        h.close()
    shutil.rmtree(home)
    log('Stopped only scenario-owned processes and removed the disposable home.')
    (evidence/'live-watcher-replacement.log').write_text('\n'.join(logs)+'\n')
