from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch


def provider():
    path = Path(__file__).resolve().parents[2] / 'plugins/memory/mempalace/__init__.py'
    spec = importlib.util.spec_from_file_location('mempalace_recall_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MemPalaceRecallProvider()


def test_requires_explicit_palace(monkeypatch, tmp_path):
    monkeypatch.delenv('MEMPALACE_PALACE_PATH', raising=False)
    p = provider()
    p.initialize('session', hermes_home=str(tmp_path))
    assert p.prefetch('anything') == ''
    assert p.get_tool_schemas() == []


def test_read_only_search(monkeypatch, tmp_path):
    monkeypatch.setenv('MEMPALACE_PALACE_PATH', str(tmp_path))
    calls = []
    searcher = types.ModuleType('mempalace.searcher')
    def search(query, **kwargs):
        calls.append((query, kwargs))
        return {'results': [{'text': 'A remembered fact'}]}
    searcher.search_memories = search
    package = types.ModuleType('mempalace')
    package.__path__ = []
    with patch.dict(sys.modules, {'mempalace': package, 'mempalace.searcher': searcher}):
        p = provider()
        p.initialize('session', hermes_home=str(tmp_path))
        p.sync_turn('secret', 'answer')
        assert 'A remembered fact' in p.prefetch('query')
        assert p.get_tool_schemas() == []
    assert calls == [('query', {'palace_path': str(tmp_path.resolve()), 'n_results': 3})]
