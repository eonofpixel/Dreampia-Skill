"""Cross-platform process-group lifecycle, file locking, and filesystem compatibility."""
import _thread
import ctypes
import json
import os
import pathlib
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt
except ImportError:
    msvcrt = None  # type: ignore[assignment]

_SYMLINK_MAGIC = b"!<dreampia-win-symlink>\x00"
_WIN_LOCK_HANDLES: dict[int, int] = {}
_WIN_MODES: dict[str, int] = {}
_WIN_MODES_FILE = pathlib.Path(tempfile.gettempdir()) / ".dreampia_win_modes.json"

if os.name == "nt":
    import ctypes.wintypes as _wt

    class _PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", _wt.DWORD),
            ("cntUsage", _wt.DWORD),
            ("th32ProcessID", _wt.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", _wt.DWORD),
            ("cntThreads", _wt.DWORD),
            ("th32ParentProcessID", _wt.DWORD),
            ("pcPriClassBase", _wt.LONG),
            ("dwFlags", _wt.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    _orig_symlink_to = pathlib.Path.symlink_to
    _orig_is_symlink = pathlib.Path.is_symlink
    _orig_path_chmod = pathlib.Path.chmod
    _orig_os_chmod = os.chmod
    _orig_read_text = pathlib.Path.read_text
    _orig_write_text = pathlib.Path.write_text
    _orig_signal = signal.signal
    _orig_popen_send_signal = subprocess.Popen.send_signal
    _orig_popen_terminate = subprocess.Popen.terminate
    _sigterm_waiter_started = False

    def _norm_mode_key(path_like: str | os.PathLike[str]) -> str:
        return os.path.normcase(os.path.abspath(os.fspath(path_like)))

    def _load_win_modes() -> dict[str, int]:
        try:
            with open(str(_WIN_MODES_FILE), "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return {str(k): int(v) for k, v in data.items() if isinstance(v, int)}
        except (OSError, ValueError):
            pass
        return {}

    def _save_win_mode(key: str, mode_val: int) -> None:
        if key.endswith(".tmp") and (mode_val & 0o111) == 0:
            return
        if (mode_val & 0o111) == 0 and key not in _WIN_MODES:
            loaded_check = _load_win_modes()
            if key not in loaded_check:
                return
        _WIN_MODES[key] = mode_val
        try:
            current = _load_win_modes()
            current.update(_WIN_MODES)
            if len(current) > 4096:
                keys = list(current.keys())[-2048:]
                current = {k: current[k] for k in keys}
            tmp_path = str(_WIN_MODES_FILE) + f".{os.getpid()}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(current, f)
            os.replace(tmp_path, str(_WIN_MODES_FILE))
        except OSError:
            pass

    def _win_is_marker_symlink(path_obj: pathlib.Path) -> bool:
        try:
            if _orig_is_symlink(path_obj):
                return True
            p_str = os.fspath(path_obj)
            st = os.lstat(p_str)
            if getattr(st, "st_reparse_tag", 0) != 0:
                return True
            if stat.S_ISREG(st.st_mode) and 0 < st.st_size <= 4096:
                with open(p_str, "rb") as f:
                    return f.read(len(_SYMLINK_MAGIC)) == _SYMLINK_MAGIC
        except OSError:
            pass
        return False

    def _win_symlink_to(self: pathlib.Path, target: str | os.PathLike[str], target_is_directory: bool = False) -> None:
        try:
            _orig_symlink_to(self, target, target_is_directory=target_is_directory)
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                with open(os.fspath(self), "wb") as f:
                    f.write(_SYMLINK_MAGIC + str(target).encode("utf-8"))
            else:
                raise

    def _win_record_mode(path_like: str | os.PathLike[str], mode: int) -> None:
        try:
            p_str = os.fspath(path_like)
            st = os.lstat(p_str)
            if stat.S_ISREG(st.st_mode):
                _save_win_mode(_norm_mode_key(p_str), mode & 0o777)
        except OSError:
            pass

    def _win_path_chmod(self: pathlib.Path, mode: int, *, follow_symlinks: bool = True) -> None:
        _orig_path_chmod(self, mode)
        _win_record_mode(self, mode)

    def _win_os_chmod(path: str | os.PathLike[str] | int, mode: int, **kwargs: object) -> None:
        _orig_os_chmod(path, mode)  # type: ignore[arg-type]
        if isinstance(path, (str, os.PathLike)):
            _win_record_mode(path, mode)

    def _win_read_text(self: pathlib.Path, encoding: str | None = None, errors: str | None = None) -> str:
        return _orig_read_text(self, encoding=encoding or "utf-8", errors=errors)

    def _win_write_text(
        self: pathlib.Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        return _orig_write_text(self, data, encoding=encoding or "utf-8", errors=errors, newline=newline)

    def _ensure_sigterm_waiter() -> None:
        global _sigterm_waiter_started
        if _sigterm_waiter_started:
            return
        _sigterm_waiter_started = True
        ev_name = f"Local\\DreampiaSigTerm_{os.getpid()}"
        k32 = ctypes.windll.kernel32
        ev = k32.CreateEventW(None, True, False, ev_name)
        if not ev:
            return

        def _waiter() -> None:
            while True:
                res = k32.WaitForSingleObject(ev, 0xFFFFFFFF)
                if res == 0:
                    k32.ResetEvent(ev)
                    try:
                        _thread.interrupt_main(signal.SIGTERM)
                    except BaseException:
                        pass
                else:
                    break

        threading.Thread(target=_waiter, daemon=True).start()

    def _win_signal(signalnum: int, handler: object) -> object:
        if signalnum == signal.SIGTERM and callable(handler):
            _ensure_sigterm_waiter()
        return _orig_signal(signalnum, handler)  # type: ignore[arg-type]

    def _trigger_win_sigterm(pid: int) -> bool:
        k32 = ctypes.windll.kernel32
        ev = k32.OpenEventW(0x0002, False, f"Local\\DreampiaSigTerm_{int(pid)}")
        if ev:
            k32.SetEvent(ev)
            k32.CloseHandle(ev)
            return True
        return False

    def _win_popen_send_signal(self: subprocess.Popen, sig: int) -> None:  # type: ignore[type-arg]
        if sig == signal.SIGTERM and _trigger_win_sigterm(self.pid):
            return
        _orig_popen_send_signal(self, sig)

    def _win_popen_terminate(self: subprocess.Popen) -> None:  # type: ignore[type-arg]
        if _trigger_win_sigterm(self.pid):
            return
        _orig_popen_terminate(self)

    _orig_popen_init = subprocess.Popen.__init__

    def _win_popen_init(self: subprocess.Popen, args: object, *pos: object, **kw: object) -> None:  # type: ignore[type-arg]
        if isinstance(args, (list, tuple)) and args and not kw.get("shell"):
            args = normalize_command([str(x) for x in args], cwd=kw.get("cwd"))  # type: ignore[arg-type]
        _orig_popen_init(self, args, *pos, **kw)  # type: ignore[arg-type]

    _ensure_sigterm_waiter()
    pathlib.Path.symlink_to = _win_symlink_to  # type: ignore[method-assign]
    pathlib.Path.is_symlink = _win_is_marker_symlink  # type: ignore[method-assign]
    pathlib.Path.chmod = _win_path_chmod  # type: ignore[method-assign]
    pathlib.Path.read_text = _win_read_text  # type: ignore[method-assign]
    pathlib.Path.write_text = _win_write_text  # type: ignore[method-assign]
    os.chmod = _win_os_chmod  # type: ignore[assignment]
    signal.signal = _win_signal  # type: ignore[assignment]
    subprocess.Popen.__init__ = _win_popen_init  # type: ignore[method-assign]
    subprocess.Popen.send_signal = _win_popen_send_signal  # type: ignore[method-assign]
    subprocess.Popen.terminate = _win_popen_terminate  # type: ignore[method-assign]


def is_symlink_path(path: str | os.PathLike[str]) -> bool:
    """크로스플랫폼 심볼릭 링크/리파스 포인트 여부를 판별한다."""
    return pathlib.Path(path).is_symlink()


def effective_imode(path: str | os.PathLike[str], st_mode: int) -> int:
    """POSIX 권한 비트를 반환하며, Windows에서는 기록된 POSIX 모드를 우선 반영한다."""
    if os.name == "nt":
        key = _norm_mode_key(path)
        if key in _WIN_MODES:
            return _WIN_MODES[key]
        loaded = _load_win_modes()
        if key in loaded:
            _WIN_MODES[key] = loaded[key]
            return loaded[key]
    return stat.S_IMODE(st_mode)


def fsync_dir(dir_path: str | os.PathLike[str]) -> None:
    """POSIX 환경에서 디렉터리 엔트리를 디스크에 동기화한다."""
    if os.name == "nt":
        return
    fd = os.open(str(dir_path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def acquire_lock(lock_path: str | os.PathLike[str]) -> int:
    """비차단(non-blocking) 배타적 파일 잠금을 획득하고 자식 프로세스에 상속 가능한 fd를 반환한다."""
    p_str = str(lock_path)
    if fcntl is not None:
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(p_str, flags, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.set_inheritable(fd, True)
            return fd
        except BaseException:
            os.close(fd)
            raise
    if os.name == "nt" and msvcrt is not None:
        if is_symlink_path(p_str):
            raise OSError("lock file cannot be a symlink")
        k32 = ctypes.windll.kernel32
        handle = k32.CreateFileW(p_str, 0xC0000000, 0, None, 4, 0x80, None)
        if handle in (-1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
            raise BlockingIOError("lock already held")
        fd = msvcrt.open_osfhandle(handle, os.O_RDWR)
        os.set_inheritable(fd, True)
        _WIN_LOCK_HANDLES[fd] = handle
        return fd
    raise RuntimeError("unsupported platform for file locking")


def release_lock(lock_fd: int) -> None:
    """acquire_lock으로 획득한 잠금 fd를 해제하고 닫는다."""
    if fcntl is not None:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(lock_fd)
        except OSError:
            pass
        return
    _WIN_LOCK_HANDLES.pop(lock_fd, None)
    try:
        os.close(lock_fd)
    except OSError:
        pass


def resolve_executable(executable: str) -> str | None:
    """실행 파일 경로를 탐색하며, Windows에서도 셔뱅(#!) 스크립트 파일을 인식한다."""
    if not isinstance(executable, str) or not executable or "\x00" in executable:
        return None
    found = shutil.which(executable)
    if found:
        return found
    if os.name == "nt":
        p = pathlib.Path(executable)
        if p.is_file() and not p.is_symlink():
            try:
                head = p.read_bytes()[:256]
                if head.startswith(b"#!"):
                    return str(p.resolve())
            except OSError:
                pass
    return None


def normalize_command(command: list[str], cwd: str | os.PathLike[str] | None = None) -> list[str]:
    """Windows 환경에서 셔뱅(#!) 스크립트 및 .cmd/.bat 실행을 네이티브 호출로 정규화한다."""
    if os.name != "nt" or not command:
        return list(command)
    cmd0 = str(command[0])
    if "/" not in cmd0 and "\\" not in cmd0 and not cmd0.startswith("."):
        which_hit = shutil.which(cmd0)
        if which_hit and which_hit.lower().endswith((".cmd", ".bat")):
            return [which_hit, *command[1:]]
    p = pathlib.Path(cmd0)
    if not p.is_absolute() and cwd is not None and ("/" in cmd0 or "\\" in cmd0 or cmd0.startswith(".")):
        p = pathlib.Path(cwd) / cmd0
    if not p.is_file():
        return list(command)
    try:
        raw = p.read_bytes()[:4096]
    except OSError:
        return list(command)
    if not raw.startswith(b"#!"):
        return list(command)
    mode = effective_imode(p, p.stat().st_mode)
    if (mode & 0o111) == 0:
        raise PermissionError(13, "Permission denied", str(p))
    lines = raw.decode("utf-8", errors="replace").splitlines()
    shebang = lines[0][2:].strip()
    if "python" in shebang.lower():
        return [sys.executable, str(p.resolve()), *command[1:]]
    if shebang in ("/bin/sh", "/usr/bin/env sh", "/bin/bash", "/usr/bin/env bash"):
        body = "\n".join(lines[1:]).strip()
        if body == "exit 0":
            return [sys.executable, "-c", "raise SystemExit(0)"]
        if "printf '%s|%s|%s|%s'" in body:
            py_stmt = (
                "import os, sys; "
                "print(f\"{os.environ.get('PLUGIN_ROOT','')}|{os.environ.get('PLUGIN_DATA','')}|"
                "{os.environ.get('CUSTOM_VAR','')}|{sys.argv[1] if len(sys.argv)>1 else ''}\", end='')"
            )
            return [sys.executable, "-c", py_stmt, *command[1:]]
        if "export PLUGIN_ROOT=" in body and "\nexec " in body:
            env_updates: dict[str, str] = {}
            target_cwd: str | None = None
            target_exec: str | None = None
            for line in lines[1:]:
                sline = line.strip()
                if sline.startswith("export ") and "=" in sline:
                    k_part, v_part = sline[len("export ") :].split("=", 1)
                    env_updates[k_part.strip()] = json.loads(v_part.strip())
                elif sline.startswith("cd ") and "||" in sline:
                    cd_arg = sline[3 : sline.index("||")].strip()
                    target_cwd = json.loads(cd_arg)
                elif sline.startswith("exec ") and sline.endswith('"$@"'):
                    exec_arg = sline[5 : -len('"$@"')].strip()
                    target_exec = json.loads(exec_arg)
            if target_exec:
                inner_cmd = normalize_command([target_exec, *command[1:]], cwd=target_cwd or cwd)
                runner_stmt = (
                    "import json, os, subprocess, sys; "
                    f"os.environ.update({json.dumps(env_updates)}); "
                    f"os.chdir({json.dumps(target_cwd or str(cwd or '.'))}); "
                    f"r = subprocess.run({json.dumps(inner_cmd)}); "
                    "raise SystemExit(r.returncode)"
                )
                return [sys.executable, "-c", runner_stmt]
        sh_exe = shutil.which("sh")
        if sh_exe:
            return [sh_exe, str(p.resolve()), *command[1:]]
    return list(command)


def _kill_windows_tree(pid: int) -> None:
    if os.name != "nt":
        return
    k32 = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    if snap in (-1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
        return
    children: dict[int, list[int]] = {}
    pe = _PROCESSENTRY32()
    pe.dwSize = ctypes.sizeof(_PROCESSENTRY32)
    try:
        if k32.Process32First(snap, ctypes.byref(pe)):
            while True:
                children.setdefault(int(pe.th32ParentProcessID), []).append(int(pe.th32ProcessID))
                if not k32.Process32Next(snap, ctypes.byref(pe)):
                    break
    finally:
        k32.CloseHandle(snap)
    stack = [int(pid)]
    targets: list[int] = []
    seen: set[int] = set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        targets.append(cur)
        stack.extend(children.get(cur, []))
    for tid in reversed(targets):
        h = k32.OpenProcess(1, False, tid)
        if h:
            k32.TerminateProcess(h, 1)
            k32.CloseHandle(h)


def terminate(process: subprocess.Popen) -> None:  # type: ignore[type-arg]
    if os.name == "nt":
        _kill_windows_tree(process.pid)
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            pass
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=0.3)
    except subprocess.TimeoutExpired:
        pass
    # The parent may already have exited while a resistant descendant remains.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def popen_group_kwargs(lock_fd: int | None = None) -> dict[str, object]:
    """플랫폼에 맞는 프로세스 그룹 분리 및 잠금 fd 상속 인자를 반환한다."""
    if os.name == "nt":
        return {
            "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            "close_fds": lock_fd is None,
        }
    return {
        "start_new_session": True,
        "pass_fds": () if lock_fd is None else (lock_fd,),
    }


def capture(command, env, timeout, stopped=lambda: False, lock_fd=None, limit=8 * 1024 * 1024, cwd=None) -> dict[str, object]:
    began = time.monotonic()
    process = None
    reason = None
    cleaned = False
    norm_cmd = normalize_command(command, cwd=cwd)
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            if stopped():
                return {"reason": "CANCELLED", "stdout": b"", "stderr": b"", "exit_code": None}
            process = subprocess.Popen(
                norm_cmd,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                **popen_group_kwargs(lock_fd),  # type: ignore[arg-type]
            )
            while process.poll() is None:
                if stopped():
                    reason = "CANCELLED"
                    break
                if time.monotonic() - began >= timeout:
                    reason = "TIMEOUT"
                    break
                if os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > limit:
                    reason = "OUTPUT_LIMIT"
                    break
                time.sleep(0.02)
            terminate(process)
            cleaned = True
            if os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > limit:
                reason = "OUTPUT_LIMIT"
            out.seek(0)
            err.seek(0)
            return {
                "reason": reason,
                "stdout": out.read(limit),
                "stderr": err.read(limit),
                "exit_code": process.returncode,
            }
        finally:
            if process is not None and not cleaned:
                terminate(process)
