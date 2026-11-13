import subprocess, json, pathlib
base=pathlib.Path('/Users/mehul/.no-mistakes/evidence/01M7B6EEDS5Y9FD8BQFR9QDJ38')
matrix=[
 ('cap-unset','unset','extension',[
  {'name':'default-off','input':{'command':'printf DEFAULT_START; sleep 1; printf DEFAULT_FINISHED'}},
  {'name':'default-explicit','input':{'command':'sleep 1; printf SHOULD_NOT_FINISH','timeout':0.2}}]),
 ('cap-subsecond','500','extension',[
  {'name':'subsecond-default','input':{'command':'printf SUBSECOND_START; sleep 2; printf SHOULD_NOT_FINISH'}},
  {'name':'subsecond-explicit','input':{'command':'printf SUBSECOND_EXPLICIT; sleep 2; printf SHOULD_NOT_FINISH','timeout':1}}]),
 ('cap-minimum','1','extension',[
  {'name':'minimum-cap','input':{'command':'sleep 1; printf SHOULD_NOT_FINISH'}}]),
 ('cap-maximum','2147483647','extension',[
  {'name':'maximum-supported','input':{'command':'printf MAXIMUM_WORKS'}},
  {'name':'maximum-clamps-native-invalid','input':{'command':'printf MAXIMUM_CLAMPS','timeout':2147483.648}}]),
 ('cap-above-maximum','2147483648','extension',[
  {'name':'above-maximum-ignored','input':{'command':'printf ABOVE_MAXIMUM_WORKS'}},
  {'name':'above-maximum-preserves-explicit','input':{'command':'printf RETAINED_TIMEOUT; sleep 1; printf SHOULD_NOT_FINISH','timeout':0.2}}]),
 ('cap-invalid-leading-zero','01','extension',[
  {'name':'invalid-leading-zero','input':{'command':'printf INVALID_START; sleep 1; printf INVALID_FINISHED'}}]),
 ('cap-unsafe-integer','9007199254740992','extension',[
  {'name':'unsafe-integer-ignored','input':{'command':'printf UNSAFE_INTEGER_WORKS'}}]),
 ('worker-no-extension','500','no-extension',[
  {'name':'worker-unaffected','input':{'command':'printf WORKER_START; sleep 1; printf WORKER_FINISHED'}}])
]
for label,setting,extension,cases in matrix:
 print('START '+label,flush=True)
 subprocess.run(['python3',str(base/'drive-pi.py'),label,setting,extension,json.dumps(cases)],check=True)
