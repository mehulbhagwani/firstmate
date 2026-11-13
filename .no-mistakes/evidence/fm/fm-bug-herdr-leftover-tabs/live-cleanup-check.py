import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path.cwd()
EVIDENCE = Path('/Users/mehul/.no-mistakes/evidence/01M7A38YPG1BM3MH9YEZC0FDGJ')
HELPER = ROOT / 'bin/fm-herdr-lab.sh'
fixture = Path(tempfile.mkdtemp(prefix='.test-herdr-cleanup-', dir=ROOT))
env = {k: v for k, v in os.environ.items() if not k.startswith(('FM_', 'HERDR_'))}
env['FM_HERDR_LAB_STATE_DIR'] = str(fixture / 'lab-state')
log = (EVIDENCE / 'live-cleanup-transcript.log').open('w')
results = []
session = None

def run(args, check=True, extra=None):
    active = env | (extra or {})
    p = subprocess.run([str(x) for x in args], env=active, text=True, capture_output=True)
    log.write('$ ' + ' '.join(str(x) for x in args) + '\n' + p.stdout + p.stderr + f'exit={p.returncode}\n')
    log.flush()
    if check and p.returncode:
        raise RuntimeError(f'{args}: {p.stderr or p.stdout}')
    return p

def lab(*args, check=True):
    return run([HELPER, 'run', session, *args], check=check)

def response(*args):
    return json.loads(lab(*args).stdout)['result']

def focus():
    s = response('api', 'snapshot')['snapshot']
    return s['focused_workspace_id'], s['focused_tab_id']

def record(name, detail):
    results.append({'name': name, 'result': 'pass', 'live': True, 'detail': detail})
    print(name + ': PASS', flush=True)
    log.write(json.dumps(results[-1]) + '\n')
    log.flush()

def journal(task, item, wrong=False):
    path = home / 'state' / f'{task}.herdr-presentation'
    fields = {
        'version': 2, 'task_id': task, 'projection_id': TOKEN, 'home': str(home),
        'session': session, 'workspace_id': 'w99999' if wrong else item['workspace']['workspace_id'],
        'tab_id': item['tab']['tab_id'], 'pane_id': item['root_pane']['pane_id'],
        'parent_workspace_id': anchor['workspace']['workspace_id'], 'parent_label': 'validation-anchor',
        'workspace_label': f'└ {task} · p:{TOKEN}', 'task_label': f'fm-{task}',
    }
    path.write_text(''.join(f'{k}={v}\n' for k, v in fields.items()))
    return path

def create(task):
    return response('workspace', 'create', '--cwd', ROOT, '--label', f'└ {task} · p:{TOKEN}', '--no-focus')

def cleanup():
    return run([ROOT / 'bin/fm-herdr-session-cleanup.sh'], extra=product_env)

def present(item):
    assert lab('pane', 'get', item['root_pane']['pane_id']).returncode == 0
    assert lab('tab', 'get', item['tab']['tab_id']).returncode == 0

try:
    run([ROOT / 'bin/fm-lab-home.sh', 'create', fixture / 'home'])
    home = fixture / 'home'
    (home / 'config/backend').write_text('herdr\n')
    (home / 'config/herdr-presentation-spaces').write_text('on\n')
    session = run([HELPER, 'name', 'journal']).stdout.strip()
    run([HELPER, 'provision', session])
    lab('status', '--json')
    shim = fixture / 'bin'
    shim.mkdir()
    (shim / 'herdr').write_text('''#!/usr/bin/env python3
import os, subprocess, sys
args=sys.argv[1:]
session=os.environ['HERDR_LAB_SESSION']
if args[-2:]==['--session',session]: args=args[:-2]
if any(a=='--session' or a.startswith('--session=') for a in args): sys.exit(9)
env=dict(os.environ); env['PATH']=env['HERDR_ORIGINAL_PATH']
p=subprocess.run([env['HERDR_LAB_HELPER'],'run',session,*args],env=env)
sys.exit(p.returncode)
''')
    (shim / 'herdr').chmod(0o755)
    product_env = {
        'FM_HOME': str(home), 'FM_BACKEND': 'herdr', 'HERDR_SESSION': session,
        'HERDR_LAB_SESSION': session, 'HERDR_LAB_HELPER': str(HELPER),
        'HERDR_ORIGINAL_PATH': env['PATH'], 'PATH': str(shim) + ':' + env['PATH'],
    }
    anchor = response('workspace', 'create', '--cwd', ROOT, '--label', 'validation-anchor', '--focus')
    anchor_tab = anchor['tab']['tab_id']
    initial_focus = focus()
    TOKEN = 'AbCdEfGhIjKlMnOpQrStUv'
    task = 'v2-idle'
    candidate = create(task)
    j = journal(task, candidate)
    for attempt in range(40):
        proof = run(['bash', '-c', '. "$1"; fm_backend_herdr_pane_idle_shell_pid "$2" "$3"', '_',
                     ROOT / 'bin/fm-herdr-session-cleanup.sh', session, candidate['root_pane']['pane_id']],
                    check=False, extra=product_env | {'FM_HERDR_SESSION_CLEANUP_SOURCE_ONLY': '1'})
        if proof.returncode == 0:
            break
        time.sleep(.1)
    assert proof.returncode == 0, 'idle shell proof never converged'
    lab('api', 'snapshot')
    cleanup()
    assert not j.exists(), 'confirmed closed pane retained journal'
    assert lab('tab', 'get', candidate['tab']['tab_id'], check=False).returncode != 0
    assert focus() == initial_focus
    cleanup()
    assert focus() == initial_focus
    record('Exact v2 stale-shell cleanup and repeat', {'removed_tab': candidate['tab']['tab_id'], 'journal_exists': j.exists(), 'focus': focus()})

    candidate = create('guarded-task')
    j = journal('guarded-task', candidate)
    tab = candidate['tab']['tab_id']
    pane = candidate['root_pane']['pane_id']
    run([HELPER, 'viewer', 'start', session])
    lab('tab', 'focus', tab)
    focused_before = focus()
    cleanup()
    present(candidate)
    assert j.exists() and focus() == focused_before
    run([HELPER, 'viewer', 'stop', session])
    cleanup()
    present(candidate)
    assert j.exists() and focus() == focused_before
    record('Cleanup preserves a focused task with and without a viewer', {'tab': tab, 'focus': focus(), 'journal_exists': j.exists()})
    lab('tab', 'focus', anchor_tab)

    metadata = home / 'state/guarded-task.meta'
    metadata.write_text('backend=herdr\n')
    cleanup()
    present(candidate)
    assert j.exists() and focus() == initial_focus
    metadata.unlink()
    record('Current task metadata protects the task', {'tab': tab, 'journal_exists': j.exists(), 'focus': focus()})

    journal('guarded-task', candidate, wrong=True)
    cleanup()
    present(candidate)
    assert j.exists() and focus() == initial_focus
    record('Mismatched v2 endpoint binding protects the task', {'tab': tab, 'bound_workspace': 'w99999', 'journal_exists': j.exists()})
    journal('guarded-task', candidate)
    lab('pane', 'run', pane, 'sleep 20')
    time.sleep(.2)
    lab('pane', 'process-info', '--pane', pane)
    cleanup()
    present(candidate)
    assert j.exists() and focus() == initial_focus
    record('A real foreground command protects the pane', {'pane': pane, 'journal_exists': j.exists(), 'focus': focus()})
    lab('pane', 'close', pane)
    j.unlink()

    for mode in ('close', 'move'):
        candidate = create('empty-tab-probe-' + mode)
        old_tab = candidate['tab']['tab_id']
        old_workspace = candidate['workspace']['workspace_id']
        old_pane = candidate['root_pane']['pane_id']
        if mode == 'close':
            lab('pane', 'close', old_pane)
        else:
            lab('pane', 'move', old_pane, '--tab', anchor_tab, '--split', 'right', '--no-focus')
        tab_read = lab('tab', 'get', old_tab, check=False)
        lab('workspace', 'get', old_workspace, check=False)
        lab('api', 'snapshot')
        results.append({'name': 'Zero-pane reproduction by last-pane ' + mode, 'live': True,
                        'tab_read': tab_read.stdout + tab_read.stderr, 'tab_exit': tab_read.returncode})
    print('Empty-tab probes recorded; see the real API responses.', flush=True)
finally:
    if session and (fixture / 'lab-state' / (session + '.fleet-state.json')).exists():
        p = run([HELPER, 'teardown', session], check=False)
        results.append({'name': 'Named lab teardown and fleet tripwire', 'result': 'pass' if p.returncode == 0 else 'fail'})
        if p.returncode != 0:
            print('TEARDOWN FAILED: fixture preserved at ' + str(fixture), flush=True)
        else:
            shutil.rmtree(fixture)
    else:
        shutil.rmtree(fixture)
    (EVIDENCE / 'live-cleanup-results.json').write_text(json.dumps(results, indent=2) + '\n')
    log.close()
