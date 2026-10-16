"""Opt-in offline local argv orchestration (Cross-platform, Python standard library).

Roles label actual local commands; no model or remote calls are built in.
Approved adapters are trusted code, NOT an OS/network sandbox.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import threading
import time

try:
    from . import process as _proc
except ImportError:
    import process as _proc

ROLES = {'planner', 'executor', 'reviewer', 'verifier'}
STATUSES = {'pending', 'running', 'passed', 'failed', 'blocked', 'needs_reconciliation'}
LIMIT = 65536
MAX_SOURCE = 16 * 1024 * 1024


class ContractError(ValueError):
    pass


def require(condition, message) -> None:
    if not condition:
        raise ContractError(message)


def local_path(root, name) -> Path:
    require(isinstance(name, str) and name and '\\' not in name, 'invalid local path')
    path = Path(name)
    require(not path.is_absolute() and not name.startswith('/') and '..' not in path.parts and path.parts,
            'path must be project-local without traversal')
    current = root
    for part in path.parts:
        current /= part
        require(not current.is_symlink(), 'symlink path rejected: ' + name)
    require(current.resolve().is_relative_to(root), 'path outside project')
    return current


def object_keys(value, expected) -> None:
    require(isinstance(value, dict) and set(value) == set(expected),
            'invalid contract keys; expected ' + ', '.join(expected))


def identifier(value) -> object:
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', value)


def unique_json(pairs) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def read_json(path, limit) -> object:
    require(path.is_file() and path.stat().st_size <= limit, 'missing or oversized JSON: ' + str(path))
    return json.loads(path.read_text(), object_pairs_hook=unique_json)


def load(root) -> dict[str, object]:
    contract = read_json(local_path(root, 'workflow.json'), 1024 * 1024)
    object_keys(contract, ('version', 'source_files', 'adapters', 'tasks'))
    require(type(contract['version']) is int and contract['version'] == 1, 'unsupported version')
    sources = contract['source_files']
    require(isinstance(sources, list) and 0 < len(sources) <= 256
            and all(isinstance(p, str) for p in sources)
            and len(set(sources)) == len(sources), 'invalid source_files')
    total = 0
    for name in sources:
        path = local_path(root, name)
        require(path.is_file() and path.parts[len(root.parts)] != '.workflow', 'invalid source file')
        total += path.stat().st_size
    require(total <= MAX_SOURCE, 'source fingerprint input exceeds 16 MiB')
    adapters = contract['adapters']
    require(isinstance(adapters, dict) and 0 < len(adapters) <= 64, 'invalid adapters')
    for ident, adapter in adapters.items():
        require(identifier(ident), 'invalid adapter id')
        object_keys(adapter, ('argv',))
        argv = adapter['argv']
        require(isinstance(argv, list) and 1 <= len(argv) <= 64
                and all(isinstance(a, str) and a and '\0' not in a and len(a) <= 4096 for a in argv),
                'invalid bounded argv')
        exe = Path(argv[0])
        require(exe.is_absolute() and not argv[0].startswith('/bin/') and exe.is_file() and os.access(exe, os.X_OK),
                'adapter executable must be an existing absolute executable')
        require(exe.stem.lower() not in {'sh', 'bash', 'zsh', 'dash', 'fish', 'csh', 'ksh', 'cmd', 'pwsh', 'powershell',
                                         'curl', 'wget', 'ssh', 'scp', 'nc', 'ncat', 'telnet'},
                'shell/remote executable rejected')
        for arg in argv[1:]:
            require(arg not in {'-c', '--eval', '-e'} and not arg.startswith(('http:', 'https:')),
                    'inline eval/remote argument rejected')
            require(not Path(arg).is_absolute() and not arg.startswith('/') and '..' not in Path(arg).parts,
                    'argv path must remain project-local')
            if not arg.startswith('-') and (root / arg).exists():
                local_path(root, arg)
                if (root / arg).is_file():
                    require(arg in sources, 'argv input files must be in source_files: ' + arg)
    tasks = contract['tasks']
    require(isinstance(tasks, list) and 0 < len(tasks) <= 128, 'invalid tasks')
    seen = set()
    for task in tasks:
        object_keys(task, ('id', 'role', 'adapter', 'depends_on', 'side_effect', 'timeout', 'max_attempts'))
        require(identifier(task['id']) and task['id'] not in seen, 'invalid/duplicate task id')
        require(isinstance(task['role'], str) and task['role'] in ROLES, 'invalid role')
        require(isinstance(task['adapter'], str) and task['adapter'] in adapters, 'missing adapter')
        deps = task['depends_on']
        require(isinstance(deps, list) and all(isinstance(dep, str) and dep in seen for dep in deps)
                and len(set(deps)) == len(deps), 'dependencies must reference earlier tasks (DAG order)')
        require(type(task['side_effect']) is bool, 'side_effect must be explicit boolean')
        require(type(task['timeout']) in (int, float) and math.isfinite(task['timeout'])
                and .01 <= task['timeout'] <= 300, 'timeout must be 0.01..300 seconds')
        require(type(task['max_attempts']) is int and 1 <= task['max_attempts'] <= 5,
                'max_attempts must be 1..5 total attempts')
        seen.add(task['id'])
    local_path(root, '.workflow/state.json')
    local_path(root, '.workflow/state.tmp')
    local_path(root, '.workflow/lock')
    return contract


def fingerprint(root, contract) -> str:
    require(read_json(local_path(root, 'workflow.json'), 1024 * 1024) == contract,
            'source contract changed during execution')
    digest = hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(',', ':')).encode())
    # Pin runner semantics and interpreter/executable bytes as well as declared sources.
    digest.update(Path(__file__).read_bytes())
    for name in sorted(contract['source_files']):
        path = local_path(root, name)
        require(path.is_file() and path.stat().st_size <= MAX_SOURCE, 'invalid fingerprint source')
        digest.update(name.encode() + b'\0' + hashlib.sha256(path.read_bytes()).digest())
    for executable in sorted({a['argv'][0] for a in contract['adapters'].values()}):
        digest.update(executable.encode() + b'\0' + hashlib.sha256(Path(executable).read_bytes()).digest())
    return digest.hexdigest()


def checkpoint(root, state) -> None:
    folder = local_path(root, '.workflow')
    folder.mkdir(mode=0o700, exist_ok=True)
    temporary = local_path(root, '.workflow/state.tmp')
    # O_NOFOLLOW and exclusive creation prevent a stale/symlink temp being overwritten.
    if temporary.exists():
        temporary.unlink()
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(state, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, local_path(root, '.workflow/state.json'))
    _proc.fsync_dir(folder)


def capture(argv, root, context, timeout, lock_fd) -> dict[str, object]:
    started = time.time()
    evidence = {'argv': argv, 'cwd': str(root), 'started_at': started,
                'timeout_seconds': timeout, 'exit_code': None, 'stdout': '', 'stderr': ''}
    # Deliberately do not inherit provider credentials, shell startup hooks or PYTHONPATH.
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin') if os.name == 'nt' else '/usr/bin:/bin',
           'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1',
           'HOME': str(root), 'TMPDIR': str(root / '.workflow')}
    if os.name == 'nt':
        for k in ('SYSTEMROOT', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP'):
            if k in os.environ:
                env[k] = os.environ[k]
    child = None
    streams = {'stdout': bytearray(), 'stderr': bytearray()}
    try:
        if os.name == 'nt':
            child = subprocess.Popen(argv, cwd=root, env=env, shell=False, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0),
                                     close_fds=True)
            assert child.stdin is not None
            child.stdin.write(json.dumps(context).encode())
            child.stdin.close()
            reason_box: list[str | None] = [None]
            lock = threading.Lock()

            def _reader(name: str, pipe: object) -> None:
                try:
                    while True:
                        chunk = pipe.read(4096)  # type: ignore[attr-defined]
                        if not chunk:
                            break
                        with lock:
                            buf = streams[name]
                            remaining = LIMIT - sum(len(v) for v in streams.values())
                            buf.extend(chunk[: max(0, remaining)])
                            if len(chunk) > remaining:
                                reason_box[0] = 'OUTPUT_LIMIT'
                                break
                except OSError:
                    pass

            readers = [
                threading.Thread(target=_reader, args=(name, getattr(child, name)), daemon=True)
                for name in ('stdout', 'stderr')
            ]
            for t in readers:
                t.start()
            deadline = time.monotonic() + timeout
            while child.poll() is None:
                if reason_box[0]:
                    break
                if time.monotonic() >= deadline:
                    reason_box[0] = 'TIMEOUT'
                    break
                time.sleep(0.01)
            if reason_box[0]:
                _proc.terminate(child)
            for t in readers:
                t.join(timeout=0.5)
            reason = reason_box[0]
            evidence['result'] = reason or ('PASS' if child.returncode == 0 else 'FAIL')
        else:
            child = subprocess.Popen(argv, cwd=root, env=env, shell=False, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     start_new_session=True, pass_fds=(lock_fd,))
            assert child.stdin is not None
            child.stdin.write(json.dumps(context).encode())
            child.stdin.close()
            with selectors.DefaultSelector() as selector:
                for name in streams:
                    pipe = getattr(child, name)
                    os.set_blocking(pipe.fileno(), False)
                    selector.register(pipe, selectors.EVENT_READ, name)
                deadline = time.monotonic() + timeout
                reason = None
                while selector.get_map():
                    if time.monotonic() >= deadline:
                        reason = 'TIMEOUT'
                        break
                    for key, _ in selector.select(min(.05, max(0, deadline - time.monotonic()))):
                        chunk = os.read(key.fd, 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        else:
                            buf = streams[key.data]
                            remaining = LIMIT - sum(len(v) for v in streams.values())
                            buf.extend(chunk[:remaining])
                            if len(chunk) > remaining:
                                reason = 'OUTPUT_LIMIT'
                                break
                    if reason:
                        break
                if not reason:
                    try:
                        child.wait(timeout=max(.001, deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        reason = 'TIMEOUT'
                evidence['result'] = reason or ('PASS' if child.returncode == 0 else 'FAIL')
    except OSError as exc:
        evidence.update(result='SPAWN_ERROR', stderr=str(exc))
    finally:
        if child is not None:
            # Kill the entire process group, including descendants of an exited parent.
            _proc.terminate(child)
            evidence['exit_code'] = child.returncode
            for pipe in (child.stdin, child.stdout, child.stderr):
                if pipe is not None:
                    pipe.close()
        for name, data in streams.items():
            if data:
                evidence[name] = data.decode('utf8', errors='replace')
        evidence['finished_at'] = time.time()
    return evidence


def validate_state(contract, state, root=None) -> None:
    object_keys(state, ('version', 'source_fingerprint', 'tasks'))
    require(state['version'] == 1 and isinstance(state['source_fingerprint'], str), 'invalid state version/fingerprint')
    require(isinstance(state['tasks'], dict) and set(state['tasks']) == {t['id'] for t in contract['tasks']},
            'checkpoint task mismatch')
    for task in contract['tasks']:
        row = state['tasks'][task['id']]
        object_keys(row, ('status', 'attempts', 'evidence'))
        require(isinstance(row['status'], str) and row['status'] in STATUSES, 'invalid checkpoint status')
        require(type(row['attempts']) is int and 0 <= row['attempts'] <= task['max_attempts'], 'invalid attempt count')
        require(isinstance(row['evidence'], list) and len(row['evidence']) <= row['attempts'], 'invalid evidence')
        require(row['status'] != 'passed' or row['attempts'] > 0, 'passed without execution')
        for evidence in row['evidence']:
            object_keys(evidence, ('argv', 'cwd', 'started_at', 'timeout_seconds', 'exit_code',
                                   'stdout', 'stderr', 'result', 'finished_at', 'source_fingerprint'))
            require(evidence['argv'] == contract['adapters'][task['adapter']]['argv'], 'evidence adapter mismatch')
            require(isinstance(evidence['cwd'], str) and Path(evidence['cwd']).is_absolute(), 'invalid evidence cwd')
            require(root is None or evidence['cwd'] == str(root), 'evidence project mismatch')
            require(type(evidence['timeout_seconds']) in (int, float)
                    and evidence['timeout_seconds'] == task['timeout'], 'evidence timeout mismatch')
            require(evidence['source_fingerprint'] == state['source_fingerprint'], 'evidence fingerprint mismatch')
            require(all(type(evidence[k]) in (int, float) and 0 <= evidence[k] < float('inf')
                        for k in ('started_at', 'finished_at'))
                    and evidence['finished_at'] >= evidence['started_at'], 'invalid evidence timestamps')
            require(evidence['exit_code'] is None or type(evidence['exit_code']) is int, 'invalid evidence exit')
            require(all(isinstance(evidence[k], str) for k in ('stdout', 'stderr')), 'invalid evidence output')
            require(isinstance(evidence['result'], str)
                    and evidence['result'] in ('PASS', 'FAIL', 'TIMEOUT', 'OUTPUT_LIMIT', 'SPAWN_ERROR'),
                    'invalid evidence result')
            require(evidence['result'] != 'PASS' or evidence['exit_code'] == 0, 'contradictory success evidence')
        if row['status'] == 'passed':
            require(len(row['evidence']) == row['attempts'] and row['evidence'][-1]['result'] == 'PASS'
                    and row['evidence'][-1]['exit_code'] == 0, 'passed without completed successful evidence')
            require(all(state['tasks'][dep]['status'] == 'passed' for dep in task['depends_on']),
                    'passed with incomplete dependency')


def runnable(task, row) -> bool:
    return (row['status'] != 'passed' and row['attempts'] < task['max_attempts']
            and not (task['side_effect'] and row['attempts'] > 0))


def execute(root, contract, state, lock_fd) -> None:
    for task in contract['tasks']:
        row = state['tasks'][task['id']]
        if row['status'] == 'passed':
            continue
        if task['side_effect'] and row['attempts']:
            row['status'] = 'needs_reconciliation'
            checkpoint(root, state)
            continue
        if any(state['tasks'][dep]['status'] != 'passed' for dep in task['depends_on']):
            row['status'] = 'blocked'
            checkpoint(root, state)
            continue
        if row['attempts'] >= task['max_attempts']:
            row['status'] = 'failed'
            checkpoint(root, state)
            continue
        while runnable(task, row):
            require(fingerprint(root, contract) == state['source_fingerprint'], 'source changed; new reviewed workflow required')
            row['status'] = 'running'
            row['attempts'] += 1
            checkpoint(root, state)  # persisted BEFORE actual subprocess spawn
            context = {'version': 1, 'task_id': task['id'], 'role': task['role'],
                       'attempt': row['attempts'], 'side_effect': task['side_effect'],
                       'source_fingerprint': state['source_fingerprint'],
                       'dependencies': {dep: state['tasks'][dep]['status'] for dep in task['depends_on']}}
            evidence = capture(contract['adapters'][task['adapter']]['argv'], root, context,
                               task['timeout'], lock_fd)
            evidence['source_fingerprint'] = state['source_fingerprint']
            row['evidence'].append(evidence)
            row['status'] = ('passed' if evidence['result'] == 'PASS' else
                             'needs_reconciliation' if task['side_effect'] else 'failed')
            checkpoint(root, state)
            require(fingerprint(root, contract) == state['source_fingerprint'], 'source changed during execution; evidence stale')
    checkpoint(root, state)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'run', 'status', 'resume'))
    parser.add_argument('project', type=Path)
    parser.add_argument('--approve-adapter', action='append', default=[])
    parser.add_argument('--approve-effect', action='append', default=[])
    args = parser.parse_args(argv)
    lock_fd = None
    handlers = {}
    try:
        require(not args.project.is_symlink(), 'project root symlink rejected')
        root = args.project.resolve(strict=True)
        require(root.is_dir(), 'project must be a directory')
        contract = load(root)
        current = fingerprint(root, contract)
        if args.action == 'plan':
            print(json.dumps({'contract': contract, 'source_fingerprint': current,
                              'provider_inference': 'NOT_RUN', 'remote_calls': 'NOT_RUN'}))
            return 0
        if args.action == 'status':
            state = read_json(local_path(root, '.workflow/state.json'), 256 * 1024 * 1024)
            validate_state(contract, state, root)
            require(current == state['source_fingerprint'], 'source fingerprint changed; checkpoint stale')
            print(json.dumps(state))
            return 0  # status is an inspection, not a completion claim
        folder = local_path(root, '.workflow')
        folder.mkdir(mode=0o700, exist_ok=True)
        try:
            lock_fd = _proc.acquire_lock(local_path(root, '.workflow/lock'))
        except BlockingIOError:
            raise ContractError('workflow already running (or orphan adapter still active)')
        # Re-read under the lock; approvals apply to this exact current contract.
        contract = load(root)
        current = fingerprint(root, contract)
        path = local_path(root, '.workflow/state.json')
        if args.action == 'run':
            require(not path.exists(), 'checkpoint exists; use resume')
            state = {'version': 1, 'source_fingerprint': current,
                     'tasks': {task['id']: {'status': 'pending', 'attempts': 0, 'evidence': []}
                               for task in contract['tasks']}}
        else:
            state = read_json(path, 256 * 1024 * 1024)
            validate_state(contract, state, root)
            require(current == state['source_fingerprint'], 'source fingerprint changed; do not replay stale workflow')
        approved, effects = set(args.approve_adapter), set(args.approve_effect)
        require(approved <= set(contract['adapters']), 'unknown approved adapter')
        require(effects <= {t['id'] for t in contract['tasks'] if t['side_effect']}, 'unknown effect approval')
        for task in contract['tasks']:
            if runnable(task, state['tasks'][task['id']]):
                require(task['adapter'] in approved, 'adapter requires explicit approval: ' + task['adapter'])
                require(not task['side_effect'] or task['id'] in effects,
                        'side-effect task requires explicit approval: ' + task['id'])
        def interrupted(signum, frame) -> None:
            raise KeyboardInterrupt
        sigs = [signal.SIGINT, signal.SIGTERM]
        if hasattr(signal, 'SIGBREAK'):
            sigs.append(signal.SIGBREAK)
        for sig in sigs:
            handlers[sig] = signal.signal(sig, interrupted)
        execute(root, contract, state, lock_fd)
        print(json.dumps(state))
        return 0 if all(row['status'] == 'passed' for row in state['tasks'].values()) else 1
    except KeyboardInterrupt:
        print(json.dumps({'error': 'interrupted; checkpoint retained; inspect before resume'}), file=sys.stderr)
        return 130
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 2
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
        if lock_fd is not None:
            _proc.release_lock(lock_fd)


if __name__ == '__main__':
    sys.exit(main())
