import os, pathlib, shutil, subprocess, json, shlex, sys
ROOT = pathlib.Path.cwd()
EVIDENCE = pathlib.Path('/Users/mehul/.no-mistakes/evidence/01M78S4JV9CSE8DJZX9VSYF54W')
LAB = ROOT / '.live-github'
SOCKET = LAB / 's'
assert not LAB.exists()
LAB.mkdir()
(LAB/'tools').mkdir()
(LAB/'tmp').mkdir()
for tool in ['git','treehouse','tmux','tasks-axi','gh','gh-axi','timeout','jq','rg','node']:
    path=shutil.which(tool)
    if path: (LAB/'tools'/tool).symlink_to(path)
env = {k:v for k,v in os.environ.items() if not k.startswith(('FM_', 'HERDR_', 'REX_', 'TASKS_AXI_', 'TREEHOUSE_')) and k not in ['TMUX','TMUX_PANE']}
env.update(PATH=f'{LAB}/tools:/usr/bin:/bin:/usr/sbin:/sbin', TMPDIR=str(LAB/'tmp'), GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1', GIT_AUTHOR_NAME='Retention Test', GIT_AUTHOR_EMAIL='retention@example.invalid', GIT_COMMITTER_NAME='Retention Test', GIT_COMMITTER_EMAIL='retention@example.invalid')
log=(EVIDENCE/'live-github.log').open('w')
results=[]
def emit(s):
    print(s, flush=True); print(s, file=log, flush=True)
def run(args, cwd=ROOT, e=None, expected=0):
    active=dict(env); active.update(e or {})
    emit('$ '+shlex.join(map(str,args)))
    p=subprocess.run(list(map(str,args)),cwd=cwd,env=active,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
    if p.stdout: emit(p.stdout.rstrip())
    if expected is not None and p.returncode!=expected: raise RuntimeError(f'exit {p.returncode}, expected {expected}')
    return p

def case(name, extra=None):
    home=LAB/name
    run(['bash',ROOT/'bin/fm-lab-home.sh','create',home])
    run(['git','init','-q','--bare',home/'origin.git'])
    run(['git','-C',home/'origin.git','symbolic-ref','HEAD','refs/heads/main'])
    run(['git','clone','-q',home/'origin.git',home/'project'])
    project=home/'project'
    run(['git','-C',project,'checkout','-q','-b','main'])
    (project/'baseline.txt').write_text('baseline\n')
    run(['git','-C',project,'add','baseline.txt'])
    run(['git','-C',project,'commit','-qm','Initial lab content'])
    run(['git','-C',project,'push','-q','origin','main'])
    run(['git','-C',project,'remote','set-head','origin','main'])
    ce={'FM_HOME':str(home),'FM_BACKEND':'tmux','TREEHOUSE_ROOT':str(home/'pool'), 'TMUX':env['TMUX']}
    wt=pathlib.Path(run(['treehouse','get','--lease','--no-fetch','--base','main','-b',f'fm/{name}'],cwd=project,e=ce).stdout.strip().splitlines()[-1])
    assert wt.is_relative_to(LAB), wt
    (wt/'feature.txt').write_text('reviewed content\n')
    run(['git','-C',wt,'add','feature.txt'])
    run(['git','-C',wt,'commit','-qm','Reviewed content'])
    head=run(['git','-C',wt,'rev-parse','HEAD']).stdout.strip()
    (home/'.tasks.toml').write_text('backend = "markdown"\n[markdown]\npath = "data/backlog.md"\narchive = "data/done-archive.md"\ndone_keep = 10\n')
    (home/'data/backlog.md').write_text('# Backlog\n\n## In flight\n\n## Queued\n\n## Done\n')
    run(['tasks-axi','add',name,'Live retention check','--kind','ship','--file',home/'data/backlog.md'])
    run(['tasks-axi','start',name,'--file',home/'data/backlog.md'])
    run(['tmux','-S',SOCKET,'new-window','-d','-t','firstmate','-n',f'fm-{name}','-c',wt,'sleep 3600'])
    meta=f'window=firstmate:fm-{name}\nendpoint_task_id={name}\nworktree={wt}\nproject={project}\nkind=ship\nmode=direct-PR\nbackend=tmux\nspawn_gen=live-retention-{name}\n'+(extra or '')
    (home/'state'/f'{name}.meta').write_text(meta)
    (home/'state/.last-watcher-beat').touch()
    return home,project,wt,head,ce

def teardown(c,name,expected):
    home,project,wt,head,ce=c
    before=(home/'state'/f'{name}.meta').read_bytes()
    p=run(['bash',ROOT/'bin/fm-teardown.sh',name],e=ce,expected=expected)
    if expected:
        assert 'REFUSED:' in p.stdout, p.stdout
        assert (home/'state'/f'{name}.meta').read_bytes()==before
        assert run(['git','-C',wt,'rev-parse','HEAD']).stdout.strip()==head
        assert run(['git','-C',wt,'branch','--show-current']).stdout.strip()==f'fm/{name}'
        run(['tmux','-S',SOCKET,'has-session','-t',f'firstmate:fm-{name}'])
        row=run(['tasks-axi','show',name,'--file',home/'data/backlog.md']).stdout
        assert 'state: in_flight' in row
        emit('OBSERVED: refusal retained the exact task record, branch, commit, live worker, and In flight backlog item.')
    else:
        assert not (home/'state'/f'{name}.meta').exists()
        assert run(['git','-C',wt,'status','--porcelain']).stdout.strip()==''
        assert run(['git','-C',project,'branch','--list',f'fm/{name}']).stdout.strip()==''
        assert run(['tmux','-S',SOCKET,'has-session','-t',f'firstmate:fm-{name}'],expected=None).returncode!=0
        row=run(['tasks-axi','show',name,'--file',home/'data/backlog.md']).stdout
        assert 'state: done' in row
        run(['treehouse','status'],cwd=project,e=ce)
        emit('OBSERVED: task record and branch removed, worker stopped, pool copy clean, and backlog Done.')
    results.append({'name':name,'result':'pass','live':True,'evidence':'live-github.log'})


try:
    preflight=run(['bash',ROOT/'bin/fm-remote-job-reap-orphans.sh','--dry-run'])
    assert not preflight.stdout.strip(), 'Global orphan sweep has candidates; refuse live cleanup.'
    run(['tmux','-S',SOCKET,'-f','/dev/null','new-session','-d','-s','firstmate','-n','anchor','-c',LAB,'sleep 3600'])
    pid=run(['tmux','-S',SOCKET,'display-message','-p','#{pid}']).stdout.strip()
    env['TMUX']=f'{SOCKET},{pid},0'
    for name,number,state,expected in [('open-review',5953,'OPEN',0),('closed-review',8391,'CLOSED',1),('merged-review',8380,'MERGED',0),('post-merge-followup',8380,'MERGED',1)]:
        emit('\nSCENARIO: '+name)
        url=f'https://github.com/kunchenguid/firstmate/pull/{number}'
        actual=run(['gh-axi','pr','view',str(number),'--repo','kunchenguid/firstmate','--fields','state,headRefOid,url']).stdout
        assert f'state: {state}' in actual, actual
        c=case(name,'pr='+url+'\n')
        home,project,wt,head,ce=c
        run(['git','-C',home/'origin.git','config','receive.shallowUpdate','true'])
        run(['git','-C',wt,'sparse-checkout','init','--no-cone'])
        run(['git','-C',wt,'sparse-checkout','set','--no-cone','/README.md'])
        run(['git','-C',wt,'fetch','-q','--depth=2','https://github.com/kunchenguid/firstmate.git',f'refs/pull/{number}/head'])
        run(['git','-C',wt,'reset','--hard','FETCH_HEAD'])
        if name=='post-merge-followup':
            with (wt/'README.md').open('a') as f: f.write('\nUnreviewed local follow-up.\n')
            run(['git','-C',wt,'add','README.md'])
            run(['git','-C',wt,'commit','-qm','Unreviewed follow-up'])
        head=run(['git','-C',wt,'rev-parse','HEAD']).stdout.strip()
        if state!='MERGED' or name=='post-merge-followup':
            run(['git','-C',wt,'push','-q','origin',f'HEAD:refs/heads/fm/{name}'])
        c=(home,project,wt,head,ce)
        teardown(c,name,expected)
    emit('\nAll GitHub live scenarios passed.')
except Exception as exc:
    emit('RUN ERROR: '+repr(exc))
    raise
finally:
    subprocess.run(['tmux','-S',str(SOCKET),'kill-server'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    shutil.rmtree(LAB)
    (EVIDENCE/'live-github-results.json').write_text(json.dumps(results,indent=2)+'\n')
    log.close()
