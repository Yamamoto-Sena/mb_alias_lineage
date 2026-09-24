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


def test_main_stub_runs_three_steps(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        # 実際のスクリプトが出力するはずのファイルを模擬的に生成する
        if "dr_sum_metadata.py" in cmd:
            (tmp_path / "dr_sum_columns.json").write_text("[]", encoding="utf-8")
        elif "board_parser.py" in cmd:
            (tmp_path / "board_aliases.json").write_text("[]", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["main.py", "--stub"])
    main_module.main()
    assert len(calls) == 3
    assert "dr_sum_metadata.py" in calls[0]
    assert "board_parser.py" in calls[1]
    assert "match_aliases.py" in calls[2]


def test_run_fails_when_expected_output_file_missing(monkeypatch):
    # ステップ自体はexit code 0で終わったが、期待した出力ファイルが無いケース
    monkeypatch.setattr(subprocess, "run", lambda cmd: subprocess.CompletedProcess(cmd, 0))
    try:
        main_module.run(["python", "dummy.py"], expect_file="does_not_exist.json")
        assert False, "SystemExitが発生するはず"
    except SystemExit as e:
        assert e.code == 1
