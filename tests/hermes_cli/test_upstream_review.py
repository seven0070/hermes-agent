"""Explicit upstream review must not change checkout or merge anything."""
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from hermes_cli import main as hm
from hermes_cli import update_cmd


def _result(cmd, stdout="", returncode=0):
    return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")


def test_review_lists_commits_without_merging(tmp_path, monkeypatch, capsys):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(hm, "PROJECT_ROOT", tmp_path)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        joined = " ".join(cmd)
        if "remote get-url origin" in joined:
            return _result(cmd, "https://github.com/seven0070/hermes-agent.git\n")
        if "rev-parse --is-shallow-repository" in joined:
            return _result(cmd, "false\n")
        if "rev-parse --verify FETCH_HEAD" in joined:
            return _result(cmd, "abc123\n")
        if "rev-list --count" in joined:
            return _result(cmd, "1\n")
        if "log --format=" in joined:
            return _result(cmd, "abc123 Fix bug\n")
        return _result(cmd)

    with patch("hermes_cli.config.detect_install_method", return_value="git"), \
         patch.object(update_cmd.subprocess, "run", side_effect=fake_run):
        hm.cmd_update(SimpleNamespace(upstream_review=True, check=False, branch=None))

    output = capsys.readouterr().out
    assert "Upstream-only commits: 1" in output
    assert "abc123 Fix bug" in output
    assert any(c[1:5] == ["fetch", "--no-tags", "origin", "main"] for c in calls)
    assert any("https://github.com/NousResearch/hermes-agent.git" in c for c in calls)
    assert all(not any(w in c for w in ("merge", "pull", "reset", "push")) for c in calls)


def test_review_rejects_ambiguous_combination_without_fetch(capsys):
    with pytest.raises(SystemExit) as exc:
        hm.cmd_update(SimpleNamespace(upstream_review=True, check=True, branch=None))
    assert exc.value.code == 2
    assert "cannot be combined" in capsys.readouterr().out
