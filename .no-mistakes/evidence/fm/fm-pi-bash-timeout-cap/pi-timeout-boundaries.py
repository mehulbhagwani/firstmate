import importlib.util, json, pathlib, subprocess, tempfile
path = pathlib.Path(__file__).with_name('pi-timeout-live.py')
spec = importlib.util.spec_from_file_location('driver', path)
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
d.RESULTS = json.loads((d.EVIDENCE / 'pi-timeout-results.json').read_text())
command = "printf 'SHELL_STARTED\n'; sleep 1; printf 'SHELL_FINISHED\n'"
d.run_session('unset-confirmed', None, [('unset-exact-command', command, None, None, False)])
extension = d.EXTENSION
d.EXTENSION = None
d.run_session('without-extension', '500', [('worker-without-extension-unchanged', command, None, None, False)])
with tempfile.NamedTemporaryFile(mode='w', suffix='.ts', prefix='.timeout-baseline-', dir=d.ROOT / '.pi/extensions', delete=False) as f:
    baseline = pathlib.Path(f.name)
    f.write(subprocess.check_output(['git', 'show', '427056c4181c41074ad24f051f79919330df0fa5:.pi/extensions/fm-primary-turnend-guard.ts'], text=True))
try:
    d.EXTENSION = str(baseline)
    d.run_session('pre-fix-control', '5000', [('pre-fix-omitted-outlives-cap', "printf 'SHELL_STARTED\n'; sleep 7; printf 'SHELL_FINISHED\n'", None, None, True)])
finally:
    d.EXTENSION = extension
    baseline.unlink()
quick = "printf 'SHELL_FINISHED\n'"
d.run_session('native-maximum', '2147483647', [('native-maximum-accepted', quick, None, None, False)])
d.run_session('above-native-maximum', '2147483648', [('documented-valid-cap-above-native-limit', quick, None, None, False)])
