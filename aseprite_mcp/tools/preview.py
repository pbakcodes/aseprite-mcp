"""Local preview HTTP server.

The server is a convenience for eyeballing exported PNGs, so it is scoped
as tightly as the surrounding architecture allows:

* it binds ``127.0.0.1`` explicitly. ``python -m http.server`` defaults to
  ``0.0.0.0``, which published every exported sprite to the whole LAN;
* its PID file lives in a per-user directory created with mode 0700 instead
  of a world-writable ``/tmp/aseprite_mcp_preview_<port>.pid``. The old path
  was both predictable and writable by any local user, so anybody could plant
  a PID there and have ``stop_preview_server`` deliver SIGTERM to a process
  they do not own;
* the recorded PID is only signalled when the running process still looks
  like the preview server this module started, so a recycled PID is left
  alone;
* a corrupt or stale PID file is reported and cleaned up rather than raising.
"""
import json
import os
import signal
import subprocess
import sys
import tempfile

from .. import mcp


def _state_dir() -> str:
    """Per-user directory for PID files, created 0700."""
    uid = getattr(os, "geteuid", lambda: os.getpid())()
    path = os.path.join(tempfile.gettempdir(), f"aseprite-mcp-{uid}")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def _pid_path(port: int) -> str:
    return os.path.join(_state_dir(), f"preview_{int(port)}.pid")


def _read_pid_file(path: str) -> dict | None:
    """Return the recorded state, or None when it is missing or unusable."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("pid"), int):
        return None
    return data


def _process_argv(pid: int) -> list[str] | None:
    """Argument vector of a running process, or None when it is unknowable.

    On Linux this is read from /proc as real argv tokens, so the identity
    check below can compare whole arguments instead of substrings (a port
    number matches far too eagerly as a substring of a path).

    Windows exposes no argv to an unprivileged caller, so `tasklist` gives
    only the image name. That is the platform's ceiling: the check there
    degrades to "a live python process", which is recorded in the tests.
    """
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
        )
        output = result.stdout or ""
        if str(pid) not in output:
            return None
        return [field.strip('" ') for field in output.split(",")]
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as handle:
            raw = handle.read()
    except OSError:
        return None
    return [part for part in raw.decode("utf-8", "replace").split("\0") if part]


def _pid_is_running(pid: int) -> bool:
    if os.name == "nt":
        return _process_argv(pid) is not None
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _is_our_server(pid: int, state: dict) -> bool:
    """True when `pid` is alive and still looks like our preview server.

    The recorded port and directory are compared against the live process's
    own argument vector. Where that cannot be read (a PID owned by another
    user, a platform without /proc) the process counts as foreign and is
    left untouched, which is what stops a planted PID file from having us
    signal an unrelated process.
    """
    if not _pid_is_running(pid):
        return False
    argv = _process_argv(pid)
    if not argv:
        return False
    if os.name == "nt":
        # No argv available; the most we can assert is a live Python image.
        return any("python" in field.lower() for field in argv)
    return (
        "http.server" in argv
        and str(state.get("port", "")) in argv
        and str(state.get("directory", "")) in argv
    )


@mcp.tool()
async def start_preview_server(directory: str, port: int = 8000) -> str:
    """Start a loopback-only HTTP server to preview exported sprites.

    The server listens on 127.0.0.1 only, so the served directory is not
    reachable from other machines.

    Args:
        directory: Directory to serve
        port: Port to bind (default 8000)
    """
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        return "Port must be between 1 and 65535"
    if not os.path.isdir(directory):
        return f"Directory {directory} not found"
    serve_root = os.path.realpath(directory)

    pid_file = _pid_path(port)
    state = _read_pid_file(pid_file)
    if state is not None and _is_our_server(state["pid"], state):
        return f"Preview server may already be running on port {port}"
    if os.path.exists(pid_file):
        os.remove(pid_file)

    args = [
        sys.executable, "-m", "http.server", str(port),
        "--bind", "127.0.0.1",
        "--directory", serve_root,
    ]
    popen_kwargs = {
        "cwd": serve_root,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    else:
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(args, **popen_kwargs)

    fd = os.open(pid_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"pid": proc.pid, "port": port, "directory": serve_root}, handle)

    return f"Preview server started: http://127.0.0.1:{port}/"


@mcp.tool()
async def stop_preview_server(port: int = 8000) -> str:
    """Stop the preview HTTP server for a given port.

    Args:
        port: Port to stop (default 8000)
    """
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        return "Port must be between 1 and 65535"
    pid_file = _pid_path(port)
    if not os.path.exists(pid_file):
        return f"No preview server PID found for port {port}"

    state = _read_pid_file(pid_file)
    if state is None:
        os.remove(pid_file)
        return f"Discarded an unreadable preview server PID file for port {port}"

    pid = state["pid"]
    if not _is_our_server(pid, state):
        os.remove(pid_file)
        return f"No preview server running on port {port} (stale PID {pid} left alone)"

    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                capture_output=True,
            )
        else:
            os.kill(pid, signal.SIGTERM)
    finally:
        os.remove(pid_file)

    return f"Preview server stopped on port {port}"
