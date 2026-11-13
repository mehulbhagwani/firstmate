import subprocess, os, pathlib, json, datetime, hashlib
root=pathlib.Path.cwd(); home=pathlib.Path(os.environ['FM_HOME']); ev=pathlib.Path(os.environ['EVIDENCE_DIR'])
log=(ev/'live-cli-checks.txt').open('w')
def run(args, input=None, ok=True, env=None):
    p=subprocess.run([str(root/'bin'/args[0]),*args[1:]],input=input,text=True,capture_output=True,env=env)
    log.write('$ '+' '.join(args)+'\n'+p.stdout+p.stderr+'[exit '+str(p.returncode)+']\n\n'); log.flush()
    if ok: assert p.returncode==0,(args,p.stdout,p.stderr)
    return p
show=lambda task: run(['fm-tasks-axi.sh','show',task,'--full']).stdout
before=show('lab-route'); until=(home/'until.txt').read_text()
assert 'hold_until: '+until in before and 'state: queued' in before
row=(ev/'browser-answer.tsv').read_text()
assert row.split('\t')[-1].strip()==until
out=run(['fm-captain-hold.sh','answers','--source','the captured result lavish-0fca9a3a925f8c25 sequence 1'],row)
assert 'deferred: lab-route' in out.stdout and show('lab-route')==before
for invalid in ['2099-02-29','2000-01-01','2099-7-20','nonsense',datetime.datetime.now(datetime.timezone.utc).date().isoformat()]:
    p=run(['fm-captain-hold.sh','answers','--source','invalid date attempt'],f'lab-route\tlater\tLater\t\t{invalid}\n',ok=False)
    assert p.returncode!=0 and 'skipped: lab-route' in p.stdout and show('lab-route')==before
original=json.loads((home/'payload.json').read_text()); board=home/'.lavish/bearings-board.html'; boardhash=hashlib.sha256(board.read_bytes()).hexdigest()
for name,date,typ in [('bad-calendar','2099-02-29','decision'),('today',datetime.datetime.now(datetime.timezone.utc).date().isoformat(),'decision'),('merge-card',until,'merge'),('credential-card',until,'credential')]:
    payload=json.loads(json.dumps(original)); payload['captains_call'][0]['type']=typ; payload['captains_call'][0]['options'][2]['defer_until']=date
    path=home/(name+'.json'); path.write_text(json.dumps(payload))
    p=run(['fm-bearings-board.sh','build',str(path)],ok=False)
    assert p.returncode!=0 and hashlib.sha256(board.read_bytes()).hexdigest()==boardhash
run(['fm-captain-hold.sh','hold','lab-work','--title','Release-gated work','--reason','Approve work or revisit later?','--repo','sample'])
(home/'state/.afk').write_text('away\n')
try:
    p=run(['fm-captain-hold.sh','answers','--source','dated release option'],f'lab-work\tlater\tLater\trelease\t{until}\n')
    assert 'deferred: lab-work' in p.stdout
    s=show('lab-work'); assert 'held: yes' in s and 'hold_until: '+until in s
    p=run(['fm-captain-hold.sh','answers','--source','ordinary release while away'],'lab-work\tapprove\tApprove\trelease\n',ok=False)
    assert p.returncode!=0 and 'refused:' in p.stdout and show('lab-work')==s
finally: (home/'state/.afk').unlink()
run(['fm-captain-hold.sh','hold','lab-prose','--title','Plain later label','--reason','Ordinary choice','--repo','sample'])
run(['fm-captain-hold.sh','answers','--source','unstructured label'],'lab-prose\tlater\tLater\n')
assert 'state: done' in show('lab-prose')
p=run(['fm-captain-hold.sh','answers','--source','stale closed card'],f'lab-prose\tlater\tLater\t\t{until}\n',ok=False)
assert p.returncode!=0 and 'state: done' in show('lab-prose')
run(['fm-captain-hold.sh','hold','lab-reconcile','--title','Reconcile only','--reason','Recheck current facts','--repo','sample'])
s=show('lab-reconcile')
p=run(['fm-captain-hold.sh','answers','--source','reserved reconcile'],f'lab-reconcile\treconcile\tReconcile\t\t{until}\n',ok=False)
assert p.returncode!=0 and show('lab-reconcile')==s
(home/'config/hold-pr-settle').touch()
for mode in ['close','release']:
    id='lab-policy-'+mode
    run(['fm-captain-hold.sh','hold',id,'--title','Policy decision','--reason','Staged rollout or direct rollout?','--repo','sample'])
    run(['fm-captain-hold.sh','pr-policy',id,'https://github.com/sample/sample/pull/42','merged',mode])
    policy=home/'data'/id/'hold-pr-policy.json'; assert policy.is_file()
    log.write('Existing PR policy: '+policy.read_text()+'\n')
    run(['fm-captain-hold.sh','answers','--source','dated board option'],f'{id}\tlater\tLater\t\t{until}\n')
    assert not policy.exists(); log.write('After deferral: prior PR policy is absent.\n')
    s=show(id); assert 'held: yes' in s and 'hold_until: '+until in s and 'Staged rollout or direct rollout?' in s
nowenv=os.environ.copy(); nowenv['FM_BEARINGS_NOW']=until+'T12:00:00Z'
p=run(['fm-bearings-snapshot.sh','--json'],env=nowenv); (ev/'snapshot-due.json').write_text(p.stdout)
snap=json.loads(p.stdout); due=[d for d in snap['decisions_open'] if d['id']=='lab-route']; assert len(due)==1
assert 'Staged rollout (recommended) or direct rollout?' in due[0]['question'] and 'Answer: later' not in due[0]['question']
log.write('All live CLI state assertions passed.\n'); log.close()
print('Replay, invalid dates, invalid card types, away-release guard, plain labels, closed/reconcile guards, policy invalidation, and due-date snapshot passed.')
