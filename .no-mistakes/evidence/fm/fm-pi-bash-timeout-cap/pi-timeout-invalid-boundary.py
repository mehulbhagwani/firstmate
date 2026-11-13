from pathlib import Path
p=Path('/Users/mehul/.no-mistakes/evidence/01M7APM9ZKBB32Q5HZ862S47V5')
source=(p/'pi-timeout-live.py').read_text().split('groups=[')[0]
source=source.replace('pi-timeout-verified-transcript.txt','pi-timeout-invalid-boundary-transcript.txt').replace('pi-timeout-verified-results.json','pi-timeout-invalid-boundary-results.json')
exec(compile(source,'invalid boundary live driver','exec'))
p=None
try:
    p=Pi('invalid-boundary','invalid')
    p.case('invalid-unchanged',6,None,None)
    p.case('invalid-explicit-preserved',2,.25,.25)
finally:
    if p:p.close()
if any(r['result']=='fail' for r in records): raise SystemExit(1)
