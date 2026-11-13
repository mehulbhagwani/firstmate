import json, os, pathlib, shlex, shutil, subprocess, tempfile, time
ROOT = pathlib.Path.cwd()
EVIDENCE = pathlib.Path('/Users/mehul/.no-mistakes/evidence/01M7B6EEDS5Y9FD8BQFR9QDJ38')
RESULTS = []
EXTENSION = str(ROOT / '.pi/extensions/fm-primary-turnend-guard.ts')

def shell(args, **kw):
    return subprocess.run(args, check=True, text=True, capture_output=True, **kw).stdout.strip()

def run_session(label, setting, cases):
    lab = pathlib.Path(tempfile.mkdtemp(prefix='.pi-timeout-lab-', dir=ROOT))
    socket_dir = None
    events = []
    raw = EVIDENCE / (label + '.rpc.log')
    env = dict(os.environ)
    for key in ['NO_MISTAKES_GATE', 'FM_GATE_REFUSE_BYPASS', 'FM_ROOT_OVERRIDE', 'FM_STATE_OVERRIDE', 'FM_DATA_OVERRIDE', 'FM_CONFIG_OVERRIDE', 'FM_PROJECTS_OVERRIDE', 'FM_TASK_ID', 'FM_PI_BASH_TIMEOUT_MAX_MS', 'HERDR_ENV', 'HERDR_SESSION', 'HERDR_PANE_ID', 'HERDR_SOCKET_PATH', 'TASKS_AXI_FILE', 'TASKS_AXI_BACKEND', 'TMUX']:
        env.pop(key, None)
    env.update(FM_HOME=str(lab), PI_TELEMETRY='0', PI_OFFLINE='1')
    if setting is not None:
        env['FM_PI_BASH_TIMEOUT_MAX_MS'] = setting
    offset = 0
    partial = ''
    def tmux(*args):
        return shell(['tmux', '-L', 'fm-lab', *args], env=env)
    def send(record):
        tmux('send-keys', '-t', 'primary', '-l', json.dumps(record))
        tmux('send-keys', '-t', 'primary', 'Enter')
    def read_events():
        nonlocal offset, partial
        if not raw.exists(): return []
        with raw.open('r') as f:
            f.seek(offset)
            data = f.read()
            offset = f.tell()
        partial += data
        lines = partial.split('\n')
        partial = lines.pop()
        added = []
        for line in lines:
            try: event = json.loads(line.strip())
            except (ValueError, TypeError): continue
            item = {'observed_at': time.time(), 'event': event}
            events.append(item)
            added.append(item)
        return added
    try:
        shell(['bin/fm-lab-home.sh', 'create', str(lab)], env=env)
        socket_dir = shell(['bin/fm-lab-home.sh', 'tmux-dir', str(lab)], env=env)
        env['TMUX_TMPDIR'] = socket_dir
        cli = ['pi', '--mode', 'rpc', '--offline', '--approve', '--no-session', '--no-context-files', '--no-extensions', '--no-skills', '--no-mcp', '--no-prompt-templates', '--no-themes', '--tools', 'bash', '--model', 'openai-codex/gpt-6.1-sol', '--thinking', 'low', '--system-prompt', 'Execute the exact requested Bash tool calls for a bounded integration test. Do not change any file, inspect files, run other commands, retry commands, or alter requested arguments. Report the real tool result. Obey steering messages after the tool returns.']
        if EXTENSION is not None: cli += ['-e', EXTENSION]
        tmux('new-session', '-d', '-s', 'primary', '-x', '240', '-y', '50', '-c', str(ROOT), '-e', 'FM_HOME=' + str(lab), *cli)
        tmux('pipe-pane', '-o', '-t', 'primary', 'cat > ' + shlex.quote(str(raw)))
        time.sleep(1)
        send({'id': 'ready', 'type': 'get_state'})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if any(x['event'].get('id') == 'ready' and x['event'].get('success') for x in read_events()): break
            time.sleep(.1)
        else: raise RuntimeError('Pi RPC did not become ready: ' + tmux('capture-pane', '-p', '-t', 'primary'))
        for case in cases:
            case_id, command, timeout, expected_seconds, steering = case
            start_index = len(events)
            params = {'command': command}
            if timeout is not None: params['timeout'] = timeout
            prompt = 'Call the bash tool exactly once with these exact JSON arguments: ' + json.dumps(params) + '. Do not add a timeout if omitted. Then report the result without retrying.'
            send({'id': case_id, 'type': 'prompt', 'message': prompt})
            deadline = time.monotonic() + 100
            steered = False
            settled = False
            while time.monotonic() < deadline:
                added = read_events()
                for item in added:
                    event = item['event']
                    if event.get('type') == 'tool_execution_start' and steering and not steered:
                        send({'id': case_id + '-steer1', 'type': 'steer', 'message': 'After the running Bash call returns, acknowledge STEERING_ONE_RECEIVED. Do not start another tool call.'})
                        send({'id': case_id + '-steer2', 'type': 'steer', 'message': 'Also acknowledge STEERING_TWO_RECEIVED in your final reply. Do not start another tool call.'})
                        steered = True
                    if event.get('type') == 'agent_settled': settled = True
                if settled: break
                time.sleep(.05)
            if not settled:
                send({'type': 'abort'})
                raise RuntimeError(case_id + ': Pi did not settle within 100 seconds')
            time.sleep(.1)
            read_events()
            portion = events[start_index:]
            starts = [x for x in portion if x['event'].get('type') == 'tool_execution_start']
            ends = [x for x in portion if x['event'].get('type') == 'tool_execution_end']
            assistant_messages = [x['event']['message'] for x in portion if x['event'].get('type') == 'message_end' and x['event'].get('message', {}).get('role') == 'assistant']
            texts = '\n'.join(c.get('text', '') for m in assistant_messages for c in m.get('content', []) if c.get('type') == 'text')
            tool_calls = [c for m in assistant_messages for c in m.get('content', []) if c.get('type') == 'toolCall']
            result = {'case': case_id, 'setting_ms': setting, 'requested_arguments': params, 'model_tool_calls': tool_calls, 'tool_starts': starts, 'tool_ends': ends, 'assistant_text': texts, 'steering_responses': [x for x in portion if x['event'].get('command') == 'steer'], 'settled': settled}
            if starts and ends:
                result['elapsed_seconds'] = round(ends[0]['observed_at'] - starts[0]['observed_at'], 3)
            RESULTS.append(result)
            (EVIDENCE / 'pi-timeout-results.json').write_text(json.dumps(RESULTS, indent=2) + '\n')
            print(json.dumps(result), flush=True)
            if len(starts) != 1 or len(ends) != 1:
                raise RuntimeError(case_id + ': expected one actual Bash execution')
            assert len(tool_calls) == 1 and tool_calls[0]['arguments']['command'] == command, (case_id, tool_calls)
            assert tool_calls[0]['arguments'].get('timeout') == timeout, (case_id, tool_calls)
            actual_text = '\n'.join(c.get('text', '') for c in ends[0]['event'].get('result', {}).get('content', []))
            if expected_seconds is not None:
                assert ends[0]['event'].get('isError'), (case_id, actual_text)
                assert 'timed out' in actual_text.lower(), (case_id, actual_text)
                assert abs(ends[0]['event']['durationMs'] / 1000 - expected_seconds) < .75, (case_id, result['elapsed_seconds'])
                assert 'SHELL_FINISHED' not in actual_text, (case_id, actual_text)
            else:
                assert not ends[0]['event'].get('isError'), (case_id, actual_text)
                assert 'SHELL_FINISHED' in actual_text, (case_id, actual_text)
            if steering:
                assert len(result['steering_responses']) == 2 and all(x['event'].get('success') for x in result['steering_responses']), result
                assert 'STEERING_ONE_RECEIVED' in texts and 'STEERING_TWO_RECEIVED' in texts, result
    finally:
        read_events()
        (EVIDENCE / (label + '.events.json')).write_text(json.dumps(events, indent=2) + '\n')
        if socket_dir:
            try:
                (EVIDENCE / (label + '.pane.txt')).write_text(tmux('capture-pane', '-p', '-S', '-1000', '-t', 'primary') + '\n')
                tmux('kill-server')
            finally:
                shell(['bin/fm-lab-home.sh', 'teardown', str(lab)], env=env)
        shutil.rmtree(lab)

if __name__ == '__main__':
    run_session('cap-5000', '5000', [
        ('omitted-timeout-and-steering', "printf 'SHELL_STARTED\n'; sleep 10; printf 'SHELL_FINISHED\n'", None, 5, True),
        ('explicit-60-capped', "printf 'SHELL_STARTED\n'; sleep 10; printf 'SHELL_FINISHED\n'", 60, 5, False),
        ('explicit-1-preserved', "printf 'SHELL_STARTED\n'; sleep 4; printf 'SHELL_FINISHED\n'", 1, 1, False),
        ('explicit-5-preserved', "printf 'SHELL_STARTED\n'; sleep 7; printf 'SHELL_FINISHED\n'", 5, 5, False),
        ('quick-command-completes', "printf 'SHELL_STARTED\n'; sleep 0.1; printf 'SHELL_FINISHED\n'", None, None, False),
    ])
    run_session('cap-500', '500', [
        ('subsecond-omitted', "printf 'SHELL_STARTED\n'; sleep 2; printf 'SHELL_FINISHED\n'", None, .5, False),
        ('subsecond-explicit-capped', "printf 'SHELL_STARTED\n'; sleep 2; printf 'SHELL_FINISHED\n'", 1, .5, False),
        ('subsecond-shorter-preserved', "printf 'SHELL_STARTED\n'; sleep 2; printf 'SHELL_FINISHED\n'", .2, .2, False),
    ])
    run_session('unset', None, [
        ('unset-no-timeout', "printf 'SHELL_STARTED\n'; sleep 1; printf 'SHELL_FINISHED\n'", None, None, False),
        ('unset-explicit-preserved', "printf 'SHELL_STARTED\n'; sleep 2; printf 'SHELL_FINISHED\n'", .2, .2, False),
    ])
    for label, setting in [('invalid-zero', '0'), ('invalid-text', 'invalid'), ('invalid-leading-zero', '0500'), ('invalid-unsafe-integer', '9007199254740992')]:
        run_session(label, setting, [(label, "printf 'SHELL_STARTED\n'; sleep 1; printf 'SHELL_FINISHED\n'", None, None, False)])
    print('All real Pi scenarios completed; disposable homes and private tmux servers removed.', flush=True)
