#!/usr/bin/env python3
"""Check a real authenticated SSH session outlives the connect timeout."""
import os
from pathlib import Path
import pwd
import shlex
import shutil
import signal
import socket
import subprocess
import time

root = Path.cwd()
evidence = Path(__file__).parent
lab = root / '.ssh-timeout-validation/established'
lab.mkdir(parents=True, exist_ok=True)
remote = lab / 'remote-root'
(remote / 'bin').mkdir(parents=True, exist_ok=True)
(remote / 'AGENTS.md').write_text('Isolated transport test fixture.\n')
for name in ['fm-remote-entrypoint.sh', 'fm-remote-doctor.sh', 'fm-remote-job-lib.sh',
             'fm-tasks-axi-lib.sh', 'fm-remote-herdr-owner-lib.sh', 'fm-remote-herdr-identity-lib.sh']:
    shutil.copy2(root / 'bin' / name, remote / 'bin' / name)
env = {k: v for k, v in os.environ.items() if not k.startswith(('FM_', 'GIT_'))}
env.update(GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1')
for args in [['init', '-q'], ['add', 'AGENTS.md', 'bin']]:
    subprocess.run(['git', '-C', str(remote), *args], env=env, check=True)
for key in ['host-key', 'client-key']:
    if not (lab / key).exists():
        subprocess.run(['/usr/bin/ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(lab / key)], check=True)
with socket.socket() as probe:
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
launcher = lab / 'run-entrypoint.py'
launcher.write_text(
    '#!/opt/homebrew/bin/python3\nimport os, shlex, time\n'
    'args = shlex.split(os.environ["SSH_ORIGINAL_COMMAND"])\n'
    'assert args[0] == "fm-remote-entrypoint.sh"\n'
    'time.sleep(3)\n'
    f'os.execv({str(remote / "bin/fm-remote-entrypoint.sh")!r}, args)\n'
)
launcher.chmod(0o700)
server_config = lab / 'sshd-config'
server_config.write_text(
    f'ListenAddress 127.0.0.1\nPort {port}\nHostKey {lab}/host-key\n'
    f'PidFile {lab}/sshd.pid\nAuthorizedKeysFile {lab}/client-key.pub\n'
    f'ForceCommand {launcher}\nAllowUsers {pwd.getpwuid(os.geteuid()).pw_name}\n'
    'UsePAM no\nPasswordAuthentication no\nKbdInteractiveAuthentication no\n'
    'PubkeyAuthentication yes\nStrictModes no\nPrintMotd no\nPrintLastLog no\n'
    'DisableForwarding yes\nLogLevel VERBOSE\n'
)
local = lab / 'local-home'
(local / 'data').mkdir(parents=True, exist_ok=True)
(lab / 'remote-home').mkdir(exist_ok=True)
(local / 'data/secondmates.md').write_text(
    f'- healthy-lab - transport validation (host: healthy-lab; root: {remote}; '
    f'home: {lab}/remote-home; scope: test; projects: test; added 2026-11-13)\n'
)
known_hosts = lab / 'known-hosts'
key_parts = (lab / 'host-key.pub').read_text().split()
known_hosts.write_text(f'[127.0.0.1]:{port} {key_parts[0]} {key_parts[1]}\n')
client_config = lab / 'ssh-config'
client_config.write_text(
    f'Host healthy-lab\n HostName 127.0.0.1\n Port {port}\n'
    f' IdentityFile {lab}/client-key\n IdentitiesOnly yes\n'
    f' UserKnownHostsFile {known_hosts}\n GlobalKnownHostsFile /dev/null\n'
    ' BatchMode yes\n StrictHostKeyChecking yes\n ControlMaster no\n ControlPath none\n'
)
wrapper = lab / 'native-ssh'
wrapper.write_text(f'#!/bin/sh\nexec /usr/bin/ssh -F {shlex.quote(str(client_config))} "$@"\n')
wrapper.chmod(0o700)
server_log = evidence / 'live-sshd-server.log'
server = None
with server_log.open('w') as log:
    try:
        server = subprocess.Popen(['/usr/sbin/sshd', '-D', '-e', '-f', str(server_config)],
                                  stdout=log, stderr=log, start_new_session=True)
        for _ in range(50):
            if server.poll() is not None:
                raise RuntimeError('Local sshd could not start: ' + server_log.read_text())
            if 'Server listening' in server_log.read_text():
                break
            time.sleep(0.1)
        else:
            raise RuntimeError('Local sshd never became ready')
        env.update(FM_HOME=str(local), FM_ROOT_OVERRIDE=str(root), FM_SSH_BIN=str(wrapper),
                   FM_SSH_CONNECT_TIMEOUT='1', TMPDIR=str(lab))
        command = [str(root / 'bin/fm-on.sh'), 'healthy-lab', 'fm-remote-doctor.sh', '--help']
        print('Real OpenSSH server, ephemeral test keys, strict known-host verification.', flush=True)
        print('Remote entrypoint delays 3 seconds before running the real fm-remote-doctor.sh.', flush=True)
        print('FM_SSH_CONNECT_TIMEOUT=1 ' + shlex.join(command), flush=True)
        start = time.monotonic()
        result = subprocess.run(command, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
        elapsed = time.monotonic() - start
        print(f'elapsed_seconds={elapsed:.3f}; exit={result.returncode}', flush=True)
        print('stdout:\n' + result.stdout, flush=True)
        print('stderr:\n' + (result.stderr or '<empty>'), flush=True)
        assert elapsed >= 3 and result.returncode == 2 and 'Usage:' in result.stdout
        print('Established session survived the one-second connect window and returned the remote command result.', flush=True)
    finally:
        if server is not None and server.poll() is None:
            os.killpg(server.pid, signal.SIGTERM)
            server.wait(timeout=5)
