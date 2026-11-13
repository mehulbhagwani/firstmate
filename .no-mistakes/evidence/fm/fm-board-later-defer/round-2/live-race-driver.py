import os,pathlib,subprocess,time,signal
root=pathlib.Path.cwd();home=pathlib.Path(os.environ['FM_HOME']);ev=pathlib.Path(os.environ['EVIDENCE_DIR']); log=(ev/'live-concurrent-release.txt').open('w')
def run(args,input=None):
 p=subprocess.run([str(root/'bin'/args[0]),*args[1:]],text=True,input=input,capture_output=True);log.write('$ '+' '.join(args)+'\n'+p.stdout+p.stderr+'\n');log.flush();assert p.returncode==0,p.stderr;return p.stdout
run(['fm-captain-hold.sh','hold','lab-race','--title','Concurrent rollout decision','--reason','Staged rollout or direct rollout?','--repo','sample'])
lock=home/'state/.control-lab-race.lock'
holder=subprocess.Popen(['bash','-c','source bin/fm-wake-lib.sh; fm_lock_acquire_wait "$1"; echo LOCKED; read -r release; fm_lock_release "$1"','bash',str(lock)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
assert holder.stdout.readline().strip()=='LOCKED'
tracefile=home/'race-trace.txt'; trace=tracefile.open('w'); out=(home/'race-out.txt').open('w'); proc=None
try:
 proc=subprocess.Popen(['bash','-x','bin/fm-captain-hold.sh','answers','--source','captured board deferral'],stdin=subprocess.PIPE,stdout=out,stderr=subprocess.PIPE,text=True,start_new_session=True,env={**os.environ,'BASH_XTRACEFD':str(trace.fileno())},pass_fds=(trace.fileno(),))
 proc.stdin.write('lab-race\tlater\tLater\t\t'+(home/'until.txt').read_text()+'\n');proc.stdin.close()
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  s=tracefile.read_text()
  if 'acquire_task_control_lock lab-race' in s and 'sleep 0.1' in s[s.index('acquire_task_control_lock lab-race'):]:break
  assert proc.poll() is None,'deferral exited before lock contention';time.sleep(.05)
 else:raise AssertionError('deferral never waited for control lock')
 os.killpg(proc.pid,signal.SIGSTOP)
 log.write('The real answers process passed its initial held-task check and waited for the task control lock. Paused its process group at that wait.\n');log.flush()
 holder.stdin.write('release\n');holder.stdin.flush();holder.wait(timeout=10);assert holder.returncode==0
 decision=home/'release.txt';decision.write_text('Use the staged rollout.\n')
 run(['fm-captain-hold.sh','answer','lab-race','--release','--decision-file',str(decision)])
 before=run(['fm-tasks-axi.sh','show','lab-race','--full']);assert 'held: no' in before
 os.killpg(proc.pid,signal.SIGCONT);proc.wait(timeout=30);out.close();trace.close()
 result=(home/'race-out.txt').read_text();log.write('Resumed queued deferral:\n'+result+'exit='+str(proc.returncode)+'\n');log.flush()
 after=run(['fm-tasks-axi.sh','show','lab-race','--full'])
 assert proc.returncode!=0 and 'not held for the captain' in result and before==after
 log.write('The queued deferral was refused; released task remained byte-for-byte unchanged.\n')
 print('Real concurrent chat release wins; waiting deferral refuses without re-holding work.')
finally:
 if proc and proc.poll() is None:
  os.killpg(proc.pid,signal.SIGCONT);os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
 if holder.poll() is None:
  holder.stdin.write('release\n');holder.stdin.flush();holder.wait(timeout=10)
 log.close()
