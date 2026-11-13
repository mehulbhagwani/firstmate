import json
from pathlib import Path
p=Path(__file__).parent
accepted=['live-green','live-ruleset-green','live-ruleset-green-46300','hybrid-null','hybrid-null-ruleset-green','hybrid-null-ruleset-green-46300']
refused=['live-missing','live-red','hybrid-missing-protection','hybrid-missing-key','hybrid-malformed','hybrid-null-red','hybrid-null-ruleset-hidden']
for name in accepted:
    d=p/name
    output=(d/'stdout.txt').read_text()+(d/'stderr.txt').read_text()
    calls=[json.loads(line) for line in (d/'gh-calls.jsonl').read_text().splitlines()]
    merges=[args for args in calls if args[:2]==['pr','merge']]
    assert (d/'exit.txt').read_text().strip()=='97', name
    assert 'verified: https://' in output and 'every unwaived required check reported' in output, name
    assert 'VALIDATION GUARD: refused external write' in output, name
    assert len(merges)==1 and '--match-head-commit' in merges[0], name
for name in refused:
    d=p/name
    output=(d/'stdout.txt').read_text()+(d/'stderr.txt').read_text()
    calls=[json.loads(line) for line in (d/'gh-calls.jsonl').read_text().splitlines()]
    assert (d/'exit.txt').read_text().strip()=='1', name
    assert 'error: refusing to merge' in output, name
    assert not any(args[:2]==['pr','merge'] for args in calls), name
for name,code,text in [
    ('live-park-green',0,'clean head='),
    ('live-park-missing',3,'have not reported on head'),
    ('hybrid-park-null',0,'clean head='),
    ('hybrid-park-missing-protection',3,'required checks of the base branch could not be read'),
    ('hybrid-park-missing-key',3,'required checks of the base branch could not be read'),
    ('hybrid-park-malformed',3,'required checks of the base branch could not be read')]:
    d=p/name
    assert int((d/'exit.txt').read_text())==code, name
    assert text in (d/'stdout.txt').read_text(), name
for name in ['live-missing','live-red','hybrid-null-red']:
    output=(p/name/'stderr.txt').read_text()
    for platform in ['macos','ubuntu','windows']:
        assert "check 'build ("+platform+"-latest)'" in output, name
for name in ['hybrid-missing-protection','hybrid-missing-key','hybrid-malformed']:
    assert 'branch protection summary for base branch trunk could not be read' in (p/name/'stderr.txt').read_text(), name
assert "required check 'content-linter' has not reported" in (p/'hybrid-null-ruleset-hidden'/'stderr.txt').read_text()
for d in p.iterdir():
    if not d.is_dir() or not (d/'branch-live.json').exists(): continue
    live=json.loads((d/'branch-live.json').read_text())
    consumed=json.loads((d/'branch-consumed.json').read_text())
    if d.name.startswith('live-'): assert live==consumed, d.name
assert 'reader exit=1' in (p/'null-base-reader'/'result.txt').read_text()
assert 'reader exit=0' in (p/'null-target-reader'/'result.txt').read_text()
live_names=['live-green','live-missing','live-red','live-ruleset-green','live-ruleset-green-46300','live-park-green','live-park-missing']
hybrid_names=['hybrid-null','hybrid-missing-protection','hybrid-missing-key','hybrid-malformed','hybrid-null-red','hybrid-null-ruleset-green','hybrid-null-ruleset-green-46300','hybrid-null-ruleset-hidden','hybrid-park-null','hybrid-park-missing-protection','hybrid-park-missing-key','hybrid-park-malformed']
for file,names,intro in [
    ('live-cli-transcript.txt',live_names,'Real product CLI commands and unmodified live GitHub reads. Successful merge preflights stop at the local write guard (exit 97); no merge is sent. Refused PRs never reach that guard. Review-readiness commands are read-only.'),
    ('hybrid-cli-transcript.txt',hybrid_names,'Supplemental simulations, NOT live scenarios. GitHub reads are real except for the branch protection shape named in each command; the ruleset-hidden case also removes content-linter from the reported check rollup. Forge writes are blocked. These checks cannot prove the forge itself returns the altered shapes.')]:
    parts=[intro+'\n']
    for name in names:
        d=p/name
        parts.extend(['\nSCENARIO '+name+'\n',(d/'command.txt').read_text(),'exit='+ (d/'exit.txt').read_text(),(d/'stdout.txt').read_text(),(d/'stderr.txt').read_text()])
    if file.startswith('hybrid'):
        for name in ['null-base-reader','null-target-reader']:
            parts.extend(['\nBASELINE COMPARISON '+name+'\n',(p/name/'result.txt').read_text()])
    (p/file).write_text(''.join(parts))
print('Observed CLI outputs, refusal paths, write-guard stops, shared-reader behavior, and the before/after null regression all match their expected outcomes.')
