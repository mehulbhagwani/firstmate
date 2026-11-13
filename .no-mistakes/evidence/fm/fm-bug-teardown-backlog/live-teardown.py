from pathlib import Path
import os, shutil, subprocess, json, shlex, tempfile, time
ROOT=Path('/Users/mehul/.no-mistakes/worktrees/3ffccef5245c/01M7AAZAZW9NNFVS2B8S7W072B')
EVID=Path('/Users/mehul/.no-mistakes/evidence/01M7AAZAZW9NNFVS2B8S7W072B')
LAB=Path(tempfile.mkdtemp(prefix='.fm-live-teardown-',dir=ROOT))
LOG=(EVID/'live-teardown.log').open('w')
env={k:v for k,v in os.environ.items() if not (k.startswith(('FM_','HERDR_','TASKS_AXI_','TREEHOUSE_','GIT_')) or k in ('TMUX','TMUX_PANE','NM_HOME','TERM_PROGRAM'))}
env.update(GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1',GIT_AUTHOR_NAME='Validation',GIT_AUTHOR_EMAIL='validation@example.invalid',GIT_COMMITTER_NAME='Validation',GIT_COMMITTER_EMAIL='validation@example.invalid',GIT_TERMINAL_PROMPT='0')
results=[]; sock=None

def log(s):
    print(s,flush=True); LOG.write(s+'\n'); LOG.flush()

def run(args,cwd=ROOT,ok=(0,),extra=None,quiet=False):
    e=env.copy(); e.update(extra or {})
    log('$ '+shlex.join([str(a) for a in args])+' [cwd='+str(cwd)+']')
    p=subprocess.run([str(a) for a in args],cwd=cwd,env=e,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
    if p.stdout and not quiet: log(p.stdout.rstrip())
    log('exit='+str(p.returncode))
    if p.returncode not in ok: raise RuntimeError('unexpected exit '+str(p.returncode)+': '+p.stdout)
    return p

def git(where,*args,**kwargs): return run(['git','-C',where,*args],**kwargs).stdout.strip()
def commit(where,file,body,msg):
    (Path(where)/file).write_text(body)
    git(where,'add','--',file); git(where,'commit','-qm',msg)
    return git(where,'rev-parse','HEAD')
def snapshot(wt,id):
    return {'head':git(wt,'rev-parse','HEAD'),'branch':git(wt,'branch','--show-current'),'meta':(LAB/'state'/f'{id}.meta').read_text(),'backlog':(LAB/'data/backlog.md').read_text(),'status':git(wt,'status','--porcelain','--untracked-files=all')}

def setup(id,mode='no-mistakes',imported=None,pr=None):
    project=LAB/'projects'/id
    remote=LAB/'remotes'/f'{id}.git'; remote.parent.mkdir(exist_ok=True)
    git(ROOT,'init','-q','--bare',remote)
    git(remote,'symbolic-ref','HEAD','refs/heads/main')
    git(remote,'config','receive.shallowUpdate','true')
    git(ROOT,'init','-q','-b','main',project)
    if imported:
        git(project,'fetch','--quiet','--depth=2','https://github.com/kunchenguid/firstmate.git',f'refs/pull/{imported}/head')
        h=git(project,'rev-parse','FETCH_HEAD'); base=git(project,'rev-parse',h+'^')
        git(project,'update-ref','refs/heads/main',base)
        git(project,'reset','--hard','main',quiet=True)
    else:
        commit(project,'feature.txt','baseline\n','baseline'); h=None
    git(project,'remote','add','origin',remote); git(project,'push','-q','origin','main'); git(project,'remote','set-head','origin','main')
    wt=run(['treehouse','get','--lease','--no-fetch','--base','main','--branch',f'fm/{id}'],cwd=project).stdout.strip().splitlines()[-1]
    assert wt.startswith(str(LAB)),wt
    endpoint=run(['tmux','-S',sock,'new-window','-d','-P','-F','#{session_name}:#{window_name}','-t','fm-lab','-n','fm-'+id,'-c',ROOT,'/bin/sleep','3600']).stdout.strip()
    run([ROOT/'bin/fm-tasks-axi.sh','add',id,'live teardown validation '+id,'--kind','ship'])
    run([ROOT/'bin/fm-tasks-axi.sh','start',id])
    meta=f'window={endpoint}\nendpoint_task_id={id}\nworktree={wt}\nproject={project}\nkind=ship\nmode={mode}\nbackend=tmux\nspawn_gen=live-{id}\n'
    if pr: meta+=f'pr=https://github.com/kunchenguid/firstmate/pull/{pr}\n'
    (LAB/'state'/f'{id}.meta').write_text(meta)
    (LAB/'state/.last-watcher-beat').touch()
    return project,Path(wt),h,endpoint

def teardown(id,wt,endpoint,expected):
    before=snapshot(wt,id)
    out=run([ROOT/'bin/fm-teardown.sh',id],ok=(expected,))
    rows=run([ROOT/'bin/fm-tasks-axi.sh','show',id]).stdout
    if expected:
        assert ('has work that is not landed' in out.stdout or 'has uncommitted changes' in out.stdout), out.stdout
        after=snapshot(wt,id)
        assert before==after,'refusal changed task data'
        assert 'state: in_flight' in rows,rows
        run(['tmux','-S',sock,'display-message','-p','-t',endpoint,'#{window_id}'])
        log('OBSERVED: refusal preserved HEAD, branch, working files, task metadata, backlog, and live endpoint.')
    else:
        assert not (LAB/'state'/f'{id}.meta').exists(),'task meta retained'
        assert 'state: done' in rows,rows
        windows=run(['tmux','-S',sock,'list-windows','-a','-F','#{session_name}:#{window_name}']).stdout.splitlines()
        assert endpoint not in windows,'endpoint remains'
        log('OBSERVED: cleanup closed the backlog task, removed its metadata, returned its real Treehouse slot, and closed only its lab endpoint.')
    results.append({'name':id,'result':'pass','live':True,'evidence':'live-teardown.log','reason':''})

try:
    run([ROOT/'bin/fm-lab-home.sh','create',LAB])
    (LAB/'tools').mkdir()
    for name in ['git','node','gh','gh-axi','tmux','tasks-axi','treehouse','jq','timeout']:
        tool=shutil.which(name)
        if tool: (LAB/'tools'/name).symlink_to(tool)
    env.update(PATH=str(LAB/'tools')+':/usr/bin:/bin:/usr/sbin:/sbin',FM_HOME=str(LAB),TREEHOUSE_ROOT=str(LAB/'pool'))
    (LAB/'config/backend').write_text('tmux\n')
    (LAB/'.tasks.toml').write_text('backend = "markdown"\n[markdown]\npath = "data/backlog.md"\narchive = "data/done-archive.md"\ndone_keep = 20\n')
    socketdir=run([ROOT/'bin/fm-lab-home.sh','tmux-dir',LAB]).stdout.strip()
    sock=Path(socketdir)/('tmux-'+str(os.getuid()))/'fm-lab'
    env['TMUX_TMPDIR']=socketdir
    run(['tmux','-L','fm-lab','-f','/dev/null','new-session','-d','-s','fm-lab','-n','primary','-c',ROOT,'/bin/sleep','3600'])
    serverpid=run(['tmux','-S',sock,'display-message','-p','#{pid}']).stdout.strip()
    env['TMUX']=str(sock)+','+serverpid+',0'
    log('LIVE TOOLS: real Git, GitHub readers, tasks-axi, Treehouse and a private tmux server; no test stubs, no no-mistakes binary on PATH.')
    p,wt,h,ep=setup('pushed-only')
    head=commit(wt,'feature.txt','unlanded feature\n','unlanded task'); git(wt,'push','-q','origin','HEAD:refs/heads/fm/pushed-only')
    teardown('pushed-only',wt,ep,1)
    p,wt,h,ep=setup('external-backup')
    head=commit(wt,'feature.txt','backup-only feature\n','unlanded backed-up task')
    backup=LAB/'remotes/backup.git'; git(ROOT,'init','-q','--bare',backup)
    git(wt,'remote','add','backup',backup); git(wt,'push','-q','backup','HEAD:refs/heads/firstmate-backup/external-backup')
    with (LAB/'state/external-backup.meta').open('a') as f: f.write(f'forge=external\nreview=https://review.example.invalid/123\nreview_head={head}\nbackup_remote=backup\nbackup_prefix=refs/heads/firstmate-backup\n')
    teardown('external-backup',wt,ep,1)
    p,wt,h,ep=setup('landed-content')
    commit(wt,'feature.txt','landed feature\n','task change'); git(wt,'push','-q','origin','HEAD:refs/heads/main')
    teardown('landed-content',wt,ep,0)
    p,wt,h,ep=setup('dirty-landed')
    commit(wt,'feature.txt','landed feature\n','task change'); git(wt,'push','-q','origin','HEAD:refs/heads/main')
    (wt/'new-work.txt').write_text('unfinished work\n')
    teardown('dirty-landed',wt,ep,1)
    p,wt,h,ep=setup('open-pr',mode='direct-PR',imported=5953,pr=5953)
    git(wt,'reset','--hard',h,quiet=True); git(wt,'push','-q','origin','HEAD:refs/heads/fm/open-pr')
    run(['gh-axi','pr','view','5953','--repo','kunchenguid/firstmate','--fields','state,headRefOid'])
    teardown('open-pr',wt,ep,1)
    for id,landed in [('replay-unlanded-parent',False),('replay-landed-upstream',True),('merged-head',None)]:
        p,wt,h,ep=setup(id,imported=8399,pr=8399)
        base=git(wt,'rev-parse','HEAD')
        if landed is not None:
            parent=commit(wt,'validation-upstream.txt','parent work\n','parent work')
            git(wt,'push','-q','origin','HEAD:refs/heads/'+('main' if landed else 'retained-parent'))
            git(wt,'cherry-pick',h,quiet=True)
        else:
            git(wt,'reset','--hard',h,quiet=True)
        task=git(wt,'rev-parse','HEAD')
        # Real PR 8399 is merged. Build its corresponding landed snapshot in a
        # disposable local remote, then supersede its changed file on main.
        published_tree=git(wt,'rev-parse',(task if landed else h)+'^{tree}')
        parent_for_main=parent if landed else base
        published=git(wt,'commit-tree',published_tree,'-p',parent_for_main,'-m','squash merge of published review')
        git(p,'reset','--hard',published,quiet=True)
        changed=git(wt,'diff-tree','--no-commit-id','--name-only','-r',h).splitlines()[0]
        commit(p,changed,'later default branch rewrite\n','later default branch rewrite')
        git(p,'push','-q','origin','HEAD:refs/heads/main')
        git(wt,'fetch','-q','origin','main')
        run(['git','-C',wt,'merge-tree','--write-tree','origin/main','HEAD'],ok=(1,),quiet=True)
        # Exercise refreshing a stale origin/main for the landed-upstream case.
        if landed: git(wt,'update-ref','refs/remotes/origin/main',base)
        run(['gh-axi','pr','view','8399','--repo','kunchenguid/firstmate','--fields','state,headRefOid'])
        teardown(id,wt,ep,1 if landed is False else 0)
except Exception as e:
    log('VALIDATION ERROR: '+repr(e)); results.append({'name':'driver-error','result':'fail','live':False,'evidence':'live-teardown.log','reason':str(e)})
    raise
finally:
    (EVID/'live-results.json').write_text(json.dumps(results,indent=2)+'\n')
    if sock and sock.exists():
        run(['tmux','-S',sock,'kill-server'],ok=(0,1))
    run([ROOT/'bin/fm-lab-home.sh','teardown',LAB],ok=(0,1,2))
    shutil.rmtree(LAB)
    log('CLEANUP: disposable lab files and its private tmux server removed. Evidence retained.')
    LOG.close()
