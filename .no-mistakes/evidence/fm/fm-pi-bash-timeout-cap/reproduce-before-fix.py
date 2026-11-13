import json, pathlib, subprocess
root=pathlib.Path.cwd()
evidence=pathlib.Path('/Users/mehul/.no-mistakes/evidence/01M7B6EEDS5Y9FD8BQFR9QDJ38')
snapshot=root/'.pi/extensions/.fm-pi-timeout-before-fix.ts'
assert not snapshot.exists()
cases=[
 ('base-no-cap','427056c4181c41074ad24f051f79919330df0fa5','5000',{'name':'base-omitted-timeout-exceeds-cap','input':{'command':'printf BASE_START; sleep 8; printf BASE_EXCEEDED_CAP'}}),
 ('before-boundary-fix','8db4010ccf59842c72c6869bafc6c9f704d2ac82^','2147483648',{'name':'previous-boundary-rejection','input':{'command':'printf ABOVE_MAXIMUM_WORKS'}})
]
try:
 for label,ref,setting,case in cases:
  source=subprocess.check_output(['git','show',ref+':.pi/extensions/fm-primary-turnend-guard.ts'])
  snapshot.write_bytes(source)
  print('SOURCE '+subprocess.check_output(['git','rev-parse',ref],text=True).strip(),flush=True)
  subprocess.run(['python3',str(evidence/'drive-pi.py'),label,setting,str(snapshot.relative_to(root)),json.dumps([case])],check=True)
finally:
 snapshot.unlink(missing_ok=True)

subprocess.run(['python3',str(evidence/'drive-pi.py'),'cap-unset-long','unset','extension',json.dumps([{'name':'opt-out-exceeds-five-seconds','input':{'command':'printf OPT_OUT_START; sleep 8; printf OPT_OUT_FINISHED'}}])],check=True)
