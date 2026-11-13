#!/usr/bin/env python3
"""Exercise fm-on with native OpenSSH and controlled loopback TCP endpoints."""
import contextlib
import json
import os
from pathlib import Path
import select
import shlex
import shutil
import socket
import subprocess
import time

root = Path.cwd()
scratch = root / '.ssh-timeout-validation'
evidence = Path(__file__).parent
local = scratch / 'local-home'
(local / 'data').mkdir(parents=True, exist_ok=True)
(local / 'data/secondmates.md').write_text(
    f'- timeout-lab - transport validation (host: fm-timeout-lab; root: {root}; '
    f'home: {scratch}/remote-home; scope: test; projects: test; added 2026-11-13)\n'
)
config = scratch / 'ssh-config'
wrapper = scratch / 'native-ssh'
wrapper.write_text(f'#!/bin/sh\nexec /usr/bin/ssh -F {shlex.quote(str(config))} "$@"\n')
wrapper.chmod(0o700)
env = {k: v for k, v in os.environ.items() if not k.startswith('FM_')}
env.update(FM_HOME=str(local), FM_ROOT_OVERRIDE=str(root), FM_SSH_BIN=str(wrapper))
base = scratch / 'fm-on-base.sh'
base.write_bytes(subprocess.check_output([
    'git', 'show', '427056c4181c41074ad24f051f79919330df0fa5:bin/fm-on.sh'
]))
shutil.copyfile(root / 'bin/fm-secondmate-registry-lib.sh', scratch / 'fm-secondmate-registry-lib.sh')
results = []

def run_case(name, mode, timeout_value, *, baseline=False, deadline=22):
    with contextlib.ExitStack() as stack:
        listener = stack.enter_context(socket.socket())
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        address = listener.getsockname()
        saturated = False
        if mode == 'tcp-connect':
            for _ in range(12):
                peer = stack.enter_context(socket.socket())
                peer.setblocking(False)
                peer.connect_ex(address)
                if not select.select([], [peer], [], 0.2)[1]:
                    saturated = True
                    break
            assert saturated, 'Could not make a non-responding TCP endpoint'
        config.write_text(
            f'Host fm-timeout-lab\n  HostName 127.0.0.1\n  Port {address[1]}\n'
            '  BatchMode yes\n  ConnectionAttempts 1\n  ControlMaster no\n'
            '  ControlPath none\n  UserKnownHostsFile /dev/null\n'
            '  GlobalKnownHostsFile /dev/null\n  StrictHostKeyChecking yes\n'
        )
        child_env = env.copy()
        if timeout_value is not None:
            child_env['FM_SSH_CONNECT_TIMEOUT'] = timeout_value
        command = ['bash', str(base if baseline else root / 'bin/fm-on.sh'),
                   'timeout-lab', 'fm-remote-doctor.sh', '--help']
        print(f'\nCASE: {name}', flush=True)
        print(f'endpoint={mode}; native_ssh=/usr/bin/ssh; '
              f'FM_SSH_CONNECT_TIMEOUT={timeout_value if timeout_value is not None else "unset"}', flush=True)
        print('command: ' + shlex.join(command), flush=True)
        started = time.monotonic()
        proc = subprocess.Popen(command, env=child_env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        watchdog = False
        try:
            stdout, stderr = proc.communicate(timeout=deadline)
        except subprocess.TimeoutExpired:
            watchdog = True
            proc.kill()
            stdout, stderr = proc.communicate()
        elapsed = time.monotonic() - started
        connected = None
        if mode == 'silent-banner':
            listener.settimeout(0.1)
            try:
                peer, _ = listener.accept()
                with peer:
                    peer.settimeout(0.2)
                    connected = peer.recv(512).decode(errors='replace').strip()
            except TimeoutError:
                connected = None
        print(f'elapsed_seconds={elapsed:.3f}; exit={proc.returncode}; external_deadline={watchdog}', flush=True)
        print('stdout: ' + (stdout.strip() or '<empty>'), flush=True)
        print('stderr: ' + (stderr.strip() or '<empty>'), flush=True)
        if connected:
            print('received_client_banner: ' + connected, flush=True)
        if baseline:
            passed = watchdog
            print('baseline remained blocked until the test stopped it' if passed else 'baseline unexpectedly exited', flush=True)
        elif mode == 'invalid':
            pending = bool(select.select([listener], [], [], 0)[0])
            passed = proc.returncode == 1 and 'must be a positive integer' in stderr and not pending
            print(f'connection_received={pending}', flush=True)
        else:
            expected = int(timeout_value or 15)
            lower = 0 if mode == 'tcp-connect' and timeout_value is None else expected - 0.25
            passed = not watchdog and proc.returncode == 255 and lower <= elapsed <= expected + 4
            if mode == 'tcp-connect':
                passed = passed and 'connect to host' in stderr and 'timed out' in stderr.lower()
            else:
                passed = passed and connected is not None and 'banner exchange' in stderr.lower()
        results.append(dict(name=name, passed=passed, elapsed_seconds=round(elapsed, 3),
                            exit=proc.returncode, externally_stopped=watchdog, stdout=stdout, stderr=stderr))
        assert passed, name

try:
    run_case('Before fix: one-second override leaves TCP connection blocked', 'tcp-connect', '1', baseline=True, deadline=4)
    run_case('Default: TCP connection fails within fifteen seconds plus scheduling margin', 'tcp-connect', None)
    run_case('Override: TCP connection stops at one second', 'tcp-connect', '1', deadline=6)
    run_case('Default: silent SSH banner stops at fifteen seconds', 'silent-banner', None)
    run_case('Override: silent SSH banner stops at two seconds', 'silent-banner', '2', deadline=7)
    for invalid in ['0', '-1', '1.5', 'not-a-number', '1s', ' 2 ', '999999999999999999999999999999999']:
        run_case(f'Invalid timeout {invalid!r} is rejected before connecting', 'invalid', invalid, deadline=4)
finally:
    (evidence / 'live-ssh-timeout-results.json').write_text(json.dumps(results, indent=2) + '\n')
