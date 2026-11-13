from pathlib import Path
import json, os, shutil, subprocess, tempfile, sys

root = Path.cwd()
evidence = Path('/Users/mehul/.no-mistakes/evidence/01M7A581407Z5S7G21NMCF9MSC')
scratch = Path(tempfile.mkdtemp(prefix='.live-decisions-', dir=root))
base = '427056c4181c41074ad24f051f79919330df0fa5'
env = {k: v for k, v in os.environ.items() if not k.startswith(('FM_', 'TASKS_AXI_', 'HERDR_')) and k not in ('TMUX', 'TMUX_PANE')}
results = []
if len(sys.argv) > 1 and (evidence/'live-results.json').exists():
    results = [r for r in json.loads((evidence/'live-results.json').read_text()) if r['name'] not in sys.argv[1:]]
log = None

def run(args, home=None):
    local = env.copy()
    if home:
        local['FM_HOME'] = str(home)
    p = subprocess.run([str(a) for a in args], cwd=root, env=local, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
    if log:
        log.write('$ ' + ' '.join(str(a).replace(str(scratch), '<lab>') for a in args) + '\n')
        log.write(p.stdout + p.stderr)
        log.write(f'[exit {p.returncode}]\n\n')
        log.flush()
    if p.returncode:
        raise RuntimeError(f'{args[0]} exited {p.returncode}: {p.stderr}')
    return p.stdout

def home(name):
    h = scratch / name
    run([root/'bin/fm-lab-home.sh', 'create', h])
    shutil.copyfile(root/'.tasks.toml', h/'.tasks.toml')
    (h/'data/backlog.md').write_text('## In flight\n\n## Queued\n\n## Done\n')
    return h

def append(h, text):
    log.write('Worker status protocol append:\n' + text + '\n')
    with (h/'state/task.status').open('a') as f:
        f.write(text)

def drain(h):
    return run([root/'bin/fm-wake-drain.sh'], h)

def fold(lib, h, timed=False):
    return run(['bash', '-c', '. "$1"; status_open_decisions_incremental "$2" "" "$3"', '_', lib, h/'state/task.status', 'timed' if timed else ''], h)

def scenario(name, fn):
    global log
    if len(sys.argv) > 1 and name not in sys.argv[1:]:
        return
    with (evidence/(name+'.log')).open('w') as log:
        try:
            fn()
            results.append({'name': name, 'result': 'pass'})
        except Exception as exc:
            log.write(f'FAILED: {exc}\n')
            results.append({'name': name, 'result': 'fail', 'reason': str(exc)})
    log = None
    print(json.dumps(results[-1]), flush=True)

try:
    oldbin = scratch/'baseline/bin'
    oldbin.mkdir(parents=True)
    for f in ['fm-classify-lib.sh', 'fm-timeout-lib.sh']:
        (oldbin/f).write_bytes(subprocess.check_output(['git', 'show', f'{base}:bin/{f}'], cwd=root))

    preversion = scratch/'pre-version-bump/bin'
    preversion.mkdir(parents=True)
    for f in ['fm-classify-lib.sh', 'fm-timeout-lib.sh']:
        (preversion/f).write_bytes(subprocess.check_output(['git', 'show', f'5370e0903eae1dd37901b590bb8630b035ce67b1^:bin/{f}'], cwd=root))

    def distinct():
        h = home('distinct')
        append(h, 'blocked [at=1] key=mirror: mirror refuses\nblocked [at=2] key=agent: agent refused\n')
        old = fold(oldbin/'fm-classify-lib.sh', h)
        assert 'default\tblocked\tagent refused' in old and 'mirror\tblocked' not in old, old
        log.write('Baseline reproduces the collapse into the shared default decision.\n\n')
        out = drain(h)
        assert 'task [key=mirror] blocked: mirror refuses' in out and 'task [key=agent] blocked: agent refused' in out, out
        append(h, 'resolved key=mirror: answered\n')
        out = drain(h)
        assert 'task [key=mirror]' not in out and 'task [key=agent] blocked: agent refused' in out, out
        append(h, 'resolved\tkey=agent: answered\n')
        assert 'OPEN DECISIONS' not in drain(h)
    scenario('distinct-keys', distinct)

    def boundaries():
        h = home('boundaries')
        append(h, 'blocked [key=bracket] key=bare: [key=note] preserve both losing tokens\nblocked key=bare: [key=note] preserve losing note token\nneeds-decision: [key=note] consume winning token\nblocked: legacy default\nblocked key=bad/slug: invalid key\nresolved key=bad/slug: must not close default\nresolved x=1: prose is not a transition\nworking: resolved key=bare: prose must not close bare\n')
        out = drain(h)
        for expected in ['task [key=bracket] blocked: [key=note] preserve both losing tokens', 'task [key=bare] blocked: [key=note] preserve losing note token', 'task [key=note] needs-decision: consume winning token', 'task [key=default] blocked: legacy default']:
            assert expected in out, out
        assert 'invalid key' not in out, out
        append(h, 'resolved key=bracket: first closed\nresolved [key=bare]: second closed\nresolved: [key=note] third closed\nresolved: legacy closed\n')
        assert 'OPEN DECISIONS' not in drain(h)
    scenario('precedence-and-invalid-input', boundaries)

    def divergence():
        h = home('divergence')
        captain = root/'bin/fm-captain-hold.sh'
        tasks = root/'bin/fm-tasks-axi.sh'
        run([tasks, 'add', 'task', 'Investigate route', '--kind', 'scout', '--repo', 'sample'], h)
        run([captain, 'hold', 'route-call', '--title', 'Choose route', '--reason', 'Route choice pending', '--repo', 'sample', '--origin', 'task'], h)
        append(h, 'blocked [at=1] key=route-call: north or south\n')
        assert run([captain, 'diverged'], h) == ''
        append(h, 'resolved\tkey=route-call: answered\n')
        out = run([captain, 'diverged'], h)
        assert 'route-call\ttask\troute-call\tChoose route' in out, out
        out = drain(h)
        assert 'RECORD DIVERGENCE' in out and 'route-call' in out and 'OPEN DECISIONS' not in out, out
        out = run([tasks, 'show', 'route-call', '--full'], h)
        assert 'hold_kind: captain' in out and 'held: yes' in out, out
        (h/'answer.txt').write_text('Take the north route.\n')
        run([captain, 'answer', 'route-call', '--decision-file', h/'answer.txt'], h)
        assert run([captain, 'diverged'], h) == ''
        assert 'RECORD DIVERGENCE' not in drain(h)
    scenario('held-task-divergence', divergence)

    def upgrade():
        h = home('upgrade')
        append(h, 'blocked [at=1] key=a: waiting\nneeds-decision key=b: choose\n')
        old = fold(oldbin/'fm-classify-lib.sh', h)
        oldtimed = fold(oldbin/'fm-classify-lib.sh', h, True)
        assert old.rstrip('\n') == 'default\tblocked\twaiting', old
        assert 'default\tblocked' in oldtimed and 'b\tneeds-decision' not in oldtimed, oldtimed
        for name in ['.task.open-decisions-cursor', '.task.open-decisions-cursor.timed']:
            log.write('Actual baseline cache '+name+':\n'+(h/'state'/name).read_text()+'\n\n')
        append(h, 'resolved key=a: answered\n')
        before = fold(preversion/'fm-classify-lib.sh', h)
        before_timed = fold(preversion/'fm-classify-lib.sh', h, True)
        assert 'default\tblocked' in before and 'b\tneeds-decision' not in before, before
        assert 'default\tblocked' in before_timed and 'b\tneeds-decision' not in before_timed, before_timed
        log.write('Pre-version-bump code reproduces the stale default and missing b in both caches.\n\n')
        out = drain(h)
        assert 'task [key=b] needs-decision: choose' in out and 'task [key=default]' not in out and 'task [key=a]' not in out, out
        out = fold(root/'bin/fm-classify-lib.sh', h, True)
        assert out.rstrip('\n') == 'b\tneeds-decision\tunknown\t-\tchoose', out
        append(h, 'resolved key=b: answered\n')
        assert 'OPEN DECISIONS' not in drain(h)
        assert fold(root/'bin/fm-classify-lib.sh', h, True) == ''
        for name in ['.task.open-decisions-cursor', '.task.open-decisions-cursor.timed']:
            log.write('Migrated cache '+name+':\n'+(h/'state'/name).read_text()+'\n\n')
    scenario('cache-upgrade', upgrade)
finally:
    shutil.rmtree(scratch)
    (evidence/'live-results.json').write_text(json.dumps(results, indent=2)+'\n')
if any(r['result'] != 'pass' for r in results):
    raise SystemExit(1)
