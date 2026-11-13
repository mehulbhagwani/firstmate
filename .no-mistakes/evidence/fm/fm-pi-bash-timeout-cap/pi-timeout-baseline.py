from pathlib import Path
import subprocess
root=Path.cwd()
evid=Path('/Users/mehul/.no-mistakes/evidence/01M7APM9ZKBB32Q5HZ862S47V5')
extension=root/'.pi/extensions/.fm-timeout-baseline.ts'
assert not extension.exists()
base=subprocess.run(['git','show','427056c4181c41074ad24f051f79919330df0fa5:.pi/extensions/fm-primary-turnend-guard.ts'],check=True,capture_output=True,text=True).stdout
try:
    extension.write_text(base)
    source=(evid/'pi-timeout-live.py').read_text().split('groups=[')[0]
    source=source.replace('pi-timeout-verified-transcript.txt','pi-timeout-baseline-transcript.txt').replace('pi-timeout-verified-results.json','pi-timeout-baseline-results.json').replace("ROOT/'.pi/extensions/fm-primary-turnend-guard.ts'", "ROOT/'.pi/extensions/.fm-timeout-baseline.ts'")
    exec(compile(source,'baseline live driver','exec'))
    p=None
    try:
        p=Pi('base-commit-cap-5000ms','5000')
        p.case('baseline-unbounded',6,None,None)
        log('PRE-FIX REPRODUCTION: cap configured to 5 seconds but shell completed after 6 seconds. Current target stops the same class of timeout-omitting call at 5 seconds.')
    finally:
        if p:p.close()
finally:
    extension.unlink()
