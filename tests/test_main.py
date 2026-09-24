import subprocess
import sys

import main as main_module


def test_run_success(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda cmd: subprocess.CompletedProcess(cmd, 0))
    main_module.run(["python", "dummy.py"])  # 例外・SystemExitが起きないことを確認


def test_run_failure_exits_with_returncode(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda cmd: subprocess.CompletedProcess(cmd, 1))
    try:
        main_module.run(["python", "dummy.py"])
        assert False, "SystemExitが発生するはず"
    except SystemExit as e:
        assert e.code == 1


def test_main_requires_stub_or_full_args(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py"])
    try:
        main_module.main()
        assert False, "parser.error()によりSystemExitするはず"
    except SystemExit as e:
        assert e.code == 2  # argparseのerror()はexit code 2


def test_main_stub_runs_three_steps(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run",
                         lambda cmd: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    monkeypatch.setattr(sys, "argv", ["main.py", "--stub"])
    main_module.main()
    assert len(calls) == 3
    assert "dr_sum_metadata.py" in calls[0]
    assert "board_parser.py" in calls[1]
    assert "match_aliases.py" in calls[2]
