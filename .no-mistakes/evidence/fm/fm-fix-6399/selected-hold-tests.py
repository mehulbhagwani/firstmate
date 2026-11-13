from pathlib import Path
import re, subprocess, tempfile
source = Path('tests/fm-captain-hold-lifecycle.test.sh')
selected = {
    'test_unbracketed_status_resolution_over_an_open_hold_is_signalled',
    'test_status_resolution_over_an_open_hold_is_signalled',
    'test_legitimate_holds_produce_no_divergence_signal',
}
# Keep the original call-list entries for selected cases; do not inject calls.
lines = source.read_text().splitlines(keepends=True)
text = ''.join(line for line in lines if not re.fullmatch(r'test_[A-Za-z0-9_]+\n?', line) or line.strip() in selected)
f = tempfile.NamedTemporaryFile(prefix='.local-hold-', suffix='.sh', dir='tests', mode='w', delete=False)
try:
    f.write(text)
    f.close()
    p = subprocess.run(['bash', f.name], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    Path('/Users/mehul/.no-mistakes/evidence/01M7A581407Z5S7G21NMCF9MSC/selected-hold-tests.log').write_text(p.stdout)
    print(p.stdout, end='')
    # Check executed behavior results, so a missing call cannot silently pass.
    expected = [
        'ok - an unbracketed key=<slug> resolution over an open hold is signalled',
    ]
    if p.returncode or any(item not in p.stdout for item in expected):
        raise SystemExit(p.returncode or 1)
finally:
    Path(f.name).unlink()
