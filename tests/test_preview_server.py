"""Preview HTTP server lifecycle (tools/preview.py).

These tests cover the three properties that matter for a tool that spawns a
long-lived listener: it must not publish the served directory beyond
loopback, it must not signal a process it did not start, and a damaged PID
file must not raise out of the tool.

The POSIX path runs a real server on an ephemeral port and connects to it;
the Windows branch is exercised through a mocked os.name plus a mocked
subprocess, because that branch cannot execute here.
"""
import json
import os
import socket
import stat
import subprocess
import sys
import time

import pytest
from conftest import BASE, run

from aseprite_mcp.tools import preview


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_listener(port, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.05)
    return False


@pytest.fixture()
def served(tmp_path):
    (tmp_path / "sprite.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return str(tmp_path)


@pytest.fixture()
def port():
    chosen = free_port()
    yield chosen
    run(preview.stop_preview_server(chosen))
    pid_file = preview._pid_path(chosen)
    if os.path.exists(pid_file):
        os.remove(pid_file)


# ── argument validation ───────────────────────────────────────────────

def test_start_reports_a_missing_directory():
    assert run(preview.start_preview_server(f"{BASE}/no-such-dir")) == \
        f"Directory {BASE}/no-such-dir not found"


@pytest.mark.parametrize("bad", [0, -1, 70000, "8000", True])
def test_ports_outside_the_valid_range_are_rejected(served, bad):
    assert run(preview.start_preview_server(served, bad)) == \
        "Port must be between 1 and 65535"
    assert run(preview.stop_preview_server(bad)) == \
        "Port must be between 1 and 65535"


def test_stop_without_a_pid_file_says_so():
    unused = free_port()
    assert run(preview.stop_preview_server(unused)) == \
        f"No preview server PID found for port {unused}"


# ── real lifecycle ────────────────────────────────────────────────────

def test_server_starts_serves_and_stops(served, port):
    out = run(preview.start_preview_server(served, port))
    assert out == f"Preview server started: http://127.0.0.1:{port}/"
    assert wait_for_listener(port), "server never accepted a connection"

    state = json.loads(open(preview._pid_path(port)).read())
    assert state["port"] == port
    assert state["directory"] == os.path.realpath(served)
    assert preview._pid_is_running(state["pid"])

    assert run(preview.stop_preview_server(port)) == \
        f"Preview server stopped on port {port}"
    assert not os.path.exists(preview._pid_path(port))


def test_the_listener_is_not_reachable_off_loopback(served, port):
    """0.0.0.0 would publish every exported sprite to the LAN."""
    run(preview.start_preview_server(served, port))
    assert wait_for_listener(port)

    listeners = subprocess.run(
        [sys.executable, "-c",
         "import socket,sys;"
         "s=socket.socket();s.settimeout(0.4);"
         f"sys.exit(s.connect_ex((socket.gethostbyname(socket.gethostname()), {port})))"],
        capture_output=True,
    )
    assert listeners.returncode != 0, "the preview server answered off loopback"


def test_starting_twice_on_one_port_is_refused(served, port):
    run(preview.start_preview_server(served, port))
    assert wait_for_listener(port)
    assert run(preview.start_preview_server(served, port)) == \
        f"Preview server may already be running on port {port}"


def test_a_second_start_after_stop_is_allowed(served, port):
    run(preview.start_preview_server(served, port))
    assert wait_for_listener(port)
    run(preview.stop_preview_server(port))
    assert run(preview.start_preview_server(served, port)).startswith(
        "Preview server started")


# ── PID file hygiene ──────────────────────────────────────────────────

def test_the_pid_directory_is_private_to_this_user():
    directory = preview._state_dir()
    mode = stat.S_IMODE(os.stat(directory).st_mode)
    assert mode & (stat.S_IRWXG | stat.S_IRWXO) == 0, oct(mode)


def test_the_pid_file_is_not_world_readable(served, port):
    run(preview.start_preview_server(served, port))
    mode = stat.S_IMODE(os.stat(preview._pid_path(port)).st_mode)
    assert mode & (stat.S_IRWXG | stat.S_IRWXO) == 0, oct(mode)


def test_the_pid_path_is_not_the_old_predictable_tmp_name(port):
    """The old /tmp/aseprite_mcp_preview_<port>.pid was world-writable."""
    assert preview._pid_path(port) != f"/tmp/aseprite_mcp_preview_{port}.pid"
    assert os.path.dirname(preview._pid_path(port)) != "/tmp"


@pytest.mark.parametrize("content", ["", "not json", "[]", '{"pid": "abc"}', "{}"])
def test_a_corrupt_pid_file_is_discarded_not_raised(port, content):
    with open(preview._pid_path(port), "w", encoding="utf-8") as handle:
        handle.write(content)
    assert run(preview.stop_preview_server(port)) == \
        f"Discarded an unreadable preview server PID file for port {port}"
    assert not os.path.exists(preview._pid_path(port))


def test_a_corrupt_pid_file_does_not_block_a_fresh_start(served, port):
    with open(preview._pid_path(port), "w", encoding="utf-8") as handle:
        handle.write("garbage")
    assert run(preview.start_preview_server(served, port)).startswith(
        "Preview server started")


def test_a_stale_pid_is_reported_and_never_signalled(port):
    """A PID that is not our server must be left alone, not SIGTERM'd."""
    victim = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        with open(preview._pid_path(port), "w", encoding="utf-8") as handle:
            json.dump({"pid": victim.pid, "port": port, "directory": "/tmp"}, handle)

        result = run(preview.stop_preview_server(port))
        assert result == (
            f"No preview server running on port {port} "
            f"(stale PID {victim.pid} left alone)"
        )
        assert victim.poll() is None, "an unrelated process was signalled"
        assert not os.path.exists(preview._pid_path(port))
    finally:
        victim.kill()
        victim.wait()


def test_a_dead_pid_is_reported_as_stale(port):
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    with open(preview._pid_path(port), "w", encoding="utf-8") as handle:
        json.dump({"pid": dead.pid, "port": port, "directory": "/tmp"}, handle)
    assert "stale PID" in run(preview.stop_preview_server(port))


def test_a_planted_pid_does_not_block_a_legitimate_start(served, port):
    """Same primitive from the other side: a planted PID must not be able to
    convince the tool a server is already running."""
    victim = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        with open(preview._pid_path(port), "w", encoding="utf-8") as handle:
            json.dump({"pid": victim.pid, "port": port, "directory": "/tmp"}, handle)
        assert run(preview.start_preview_server(served, port)).startswith(
            "Preview server started")
        assert victim.poll() is None
    finally:
        victim.kill()
        victim.wait()


# ── identity check ────────────────────────────────────────────────────

def test_identity_requires_port_and_directory_to_match(served, port):
    run(preview.start_preview_server(served, port))
    assert wait_for_listener(port)
    state = json.loads(open(preview._pid_path(port)).read())

    assert preview._is_our_server(state["pid"], state)
    # a substring check would match "1" inside the real port or the path;
    # comparing whole argv tokens is what makes these two false.
    assert not preview._is_our_server(state["pid"], {**state, "port": 1})
    assert not preview._is_our_server(state["pid"], {**state, "directory": "/nope"})
    assert not preview._is_our_server(state["pid"], {})


def test_pid_is_running_is_false_for_a_nonsense_pid():
    assert preview._pid_is_running(0x7FFFFFFF) is False


def test_process_argv_is_none_for_a_nonsense_pid():
    assert preview._process_argv(0x7FFFFFFF) is None


def test_process_argv_reads_whole_tokens(served, port):
    run(preview.start_preview_server(served, port))
    assert wait_for_listener(port)
    state = json.loads(open(preview._pid_path(port)).read())
    argv = preview._process_argv(state["pid"])
    assert "http.server" in argv
    assert str(port) in argv
    assert os.path.realpath(served) in argv


# ── Windows branch (mocked; it cannot run here) ───────────────────────

class FakeCompleted:
    def __init__(self, stdout=""):
        self.stdout = stdout
        self.returncode = 0


@pytest.fixture()
def windows(monkeypatch):
    """Pretend to be Windows, with tasklist/taskkill and Popen stubbed out."""
    monkeypatch.setattr(preview.os, "name", "nt")
    monkeypatch.setattr(preview.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200,
                        raising=False)
    monkeypatch.setattr(preview.subprocess, "DETACHED_PROCESS", 0x8, raising=False)
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[0] == "tasklist":
            pid = args[2].split()[-1]
            return FakeCompleted(f'"python.exe","{pid}","Console","1","5 000 K"')
        return FakeCompleted()

    monkeypatch.setattr(preview.subprocess, "run", fake_run)
    return calls


def test_windows_start_uses_a_detached_process_group(served, windows, monkeypatch):
    port = free_port()
    captured = {}

    class FakeProc:
        pid = 4242

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProc()

    monkeypatch.setattr(preview.subprocess, "Popen", fake_popen)
    try:
        assert run(preview.start_preview_server(served, port)).startswith(
            "Preview server started")
        assert "--bind" in captured["args"]
        assert captured["args"][captured["args"].index("--bind") + 1] == "127.0.0.1"
        assert captured["kwargs"]["creationflags"] == 0x208
        assert "start_new_session" not in captured["kwargs"]
        assert json.loads(open(preview._pid_path(port)).read())["pid"] == 4242
    finally:
        os.remove(preview._pid_path(port))


def test_windows_stop_uses_taskkill(served, windows, monkeypatch):
    port = free_port()
    with open(preview._pid_path(port), "w", encoding="utf-8") as handle:
        json.dump({"pid": 4242, "port": port,
                   "directory": os.path.realpath(served)}, handle)
    monkeypatch.setattr(
        preview, "_process_argv",
        lambda pid: ["python.exe", str(pid), "Console", "1", "5 000 K"])
    assert run(preview.stop_preview_server(port)) == \
        f"Preview server stopped on port {port}"
    assert ["taskkill", "/PID", "4242", "/T", "/F"] in windows
    assert not os.path.exists(preview._pid_path(port))


def test_windows_liveness_goes_through_tasklist(windows):
    assert preview._pid_is_running(4242) is True
    assert any(call[0] == "tasklist" for call in windows)


def test_windows_identity_degrades_to_a_live_python_image(windows):
    """Windows exposes no argv, so the check can only assert the image."""
    assert preview._is_our_server(4242, {"port": 1, "directory": "/nope"}) is True


def test_windows_identity_rejects_a_non_python_image(windows, monkeypatch):
    monkeypatch.setattr(
        preview.subprocess, "run",
        lambda *a, **k: FakeCompleted('"notepad.exe","4242","Console","1","900 K"'))
    assert preview._is_our_server(4242, {"port": 1, "directory": "/nope"}) is False


def test_windows_reports_an_absent_pid_as_dead(windows, monkeypatch):
    monkeypatch.setattr(preview.subprocess, "run",
                        lambda *a, **k: FakeCompleted("INFO: No tasks are running"))
    assert preview._pid_is_running(4242) is False
    assert preview._process_argv(4242) is None
