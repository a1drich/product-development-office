import os
import socket
import subprocess
import sys
import time

import pytest

from office import ports
from office.ports import Leases, in_use, label, parse_range, stop_listeners


def leases(tmp_path, busy=(), fixed=None, reserved=("3000-3099",), agent="40000-40029"):
    return Leases(tmp_path / "leases", "acme__app", agent, 10, list(reserved), fixed or {},
                  probe=lambda p: p in busy)


def test_ranges():
    assert parse_range("40000-40009") == range(40000, 40010)
    assert parse_range("3011") == range(3011, 3012)
    assert label(range(40000, 40010)) == "40000-40009"


def test_each_run_gets_its_own_free_block(tmp_path):
    lz = leases(tmp_path, busy={40003})  # something already listens in the first block
    a, b = lz.lease(1), lz.lease(2)
    assert (a, b) == (range(40010, 40020), range(40020, 40030))
    assert lz.lease(3) is None  # all blocks taken or busy
    assert lz.release(1) == list(range(40010, 40020))
    assert lz.lease(3) == range(40010, 40020)


def test_reserved_ranges_are_never_leased(tmp_path):
    lz = leases(tmp_path, agent="3000-3119", reserved=("3000-3099",))
    assert lz.lease(1) == range(3100, 3110)


def test_fixed_sets_go_to_one_issue_at_a_time(tmp_path):
    lz = leases(tmp_path, fixed={"oauth": [3011, 3012]})
    assert lz.claim("oauth", 5) == ([3011, 3012], "")
    assert lz.claim("oauth", 5) == ([3011, 3012], "")  # claiming again is fine
    ports_, why = lz.claim("oauth", 6)
    assert ports_ is None and "held by #5" in why
    assert 3011 in lz.held_by(5) and lz.held_by(6) == []
    lz.release(6)  # releasing another issue doesn't touch it
    assert lz.claim("oauth", 6)[0] is None
    lz.release(5)
    assert lz.claim("oauth", 6) == ([3011, 3012], "")


def test_a_fixed_set_in_use_outside_the_office_is_not_claimed(tmp_path):
    lz = leases(tmp_path, busy={3012}, fixed={"oauth": [3011, 3012]})
    ports_, why = lz.claim("oauth", 5)
    assert ports_ is None and "3012" in why
    assert not (tmp_path / "leases" / "acme__app.fixed-oauth.json").exists()


def test_unknown_fixed_set(tmp_path):
    ports_, why = leases(tmp_path).claim("stripe", 1)
    assert ports_ is None and "none are configured" in why


def test_table_and_clear(tmp_path):
    lz = leases(tmp_path, fixed={"oauth": [3011, 3012]})
    lz.lease(4)
    lz.claim("oauth", 4)
    assert lz.table() == [("ports", 4, "40000-40009"), ("oauth", 4, "3011, 3012")]
    lz.clear()
    assert lz.table() == []


def test_the_cli_claims_for_the_agents_issue(tmp_path, monkeypatch, capsys):
    from office.config import Config

    cfg = Config(fixed_ports={"oauth": [45011, 45012]})
    monkeypatch.setattr(Config, "load", classmethod(lambda cls: cfg))
    monkeypatch.setattr(ports, "in_use", lambda p: False)
    monkeypatch.setenv("OFFICE_ISSUE", "7")
    monkeypatch.setenv("OFFICE_LEASES", str(tmp_path))
    monkeypatch.setenv("OFFICE_REPO", "acme/app")
    monkeypatch.setenv("OFFICE_PID", str(os.getpid()))
    assert ports.cli(["oauth"]) == 0
    assert capsys.readouterr().out.strip() == "45011 45012"
    monkeypatch.setenv("OFFICE_ISSUE", "8")
    assert ports.cli(["oauth"]) == 1
    assert "held by #7" in capsys.readouterr().err


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_probe_and_stop_against_a_real_server():
    port = free_port()
    assert not in_use(port)
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port),
                               "--bind", "127.0.0.1"], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            if in_use(port):
                break
            time.sleep(0.1)
        assert in_use(port)
        assert server.pid in stop_listeners([port])
        server.wait(timeout=5)
    finally:
        if server.poll() is None:
            server.kill()
    assert not in_use(port)


@pytest.mark.parametrize("busy", [True, False])
def test_lease_uses_the_real_probe_by_default(tmp_path, busy):
    port = free_port()
    lz = Leases(tmp_path, "acme__app", f"{port}-{port}", 1, [], {})
    if busy:
        with socket.socket() as s:
            s.bind(("127.0.0.1", port))
            s.listen()
            assert lz.lease(1) is None
    else:
        assert lz.lease(1) == range(port, port + 1)


def test_offices_on_different_repos_never_share_ports(tmp_path):
    a = leases(tmp_path, fixed={"oauth": [40005]})
    b = Leases(tmp_path / "leases", "acme__site", "40000-40029", 10, [], {"oauth": [40005]},
               probe=lambda p: False)
    assert a.lease(1) == range(40000, 40010)
    assert b.lease(1) == range(40010, 40020)  # repo a's block is taken, whoever asks
    ports_, why = b.claim("oauth", 2)  # inside repo a's block
    assert ports_ is None and "another agent's lease" in why
    b.clear()  # clearing one repo's leftovers leaves the other's leases alone
    assert a.table() == [("ports", 1, "40000-40009")] and b.table() == []


def test_a_lease_whose_office_exited_no_longer_holds_its_ports(tmp_path):
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    gone = Leases(tmp_path / "leases", "acme__site", "40000-40009", 10, [], {},
                  probe=lambda p: False, pid=dead.pid)
    assert gone.lease(1) == range(40000, 40010)
    assert leases(tmp_path, agent="40000-40009").lease(1) == range(40000, 40010)
