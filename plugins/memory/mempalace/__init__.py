"""Opt-in read-only MemPalace recall; Hermes' built-in memory stays writer.

This provider deliberately does not mirror live turns, delegation, or memory
writes. It searches a palace populated by the user separately, so it cannot
create duplicate records or silently change the built-in memory store.
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider

logger = logging.getLogger(__name__)


class MemPalaceRecallProvider(MemoryProvider):
    @property
    def name(self) -> str:
        return "mempalace"

    def __init__(self) -> None:
        self._palace: Optional[Path] = None
        self._available = False

    def is_available(self) -> bool:
        import os
        configured = os.getenv("MEMPALACE_PALACE_PATH", "").strip()
        return bool(configured and Path(configured).expanduser().is_dir() and importlib.util.find_spec("mempalace") is not None)

    def unavailable_reason(self) -> str:
        return "Install mempalace in Hermes' Python environment and set MEMPALACE_PALACE_PATH to an existing palace."

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        import os
        configured = os.getenv("MEMPALACE_PALACE_PATH", "").strip()
        # Explicit path avoids crossing profiles or inadvertently searching a
        # global palace owned by another application. No directories created.
        if not configured:
            logger.warning("MemPalace recall disabled: MEMPALACE_PALACE_PATH is required")
            return
        palace = Path(configured).expanduser().resolve()
        if not palace.is_dir():
            logger.warning("MemPalace recall disabled: configured palace does not exist")
            return
        self._palace = palace
        self._available = True

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if not self._available or not query.strip() or self._palace is None:
            return ""
        try:
            from mempalace.searcher import search_memories
            result = search_memories(query, palace_path=str(self._palace), n_results=3)
            hits = result.get("results", []) if isinstance(result, dict) else []
            lines = []
            for hit in hits[:3]:
                if not isinstance(hit, dict):
                    continue
                text = str(hit.get("text") or "").strip()
                if text:
                    lines.append(text[:1000])
            return "## MemPalace recall (external, read-only)\n" + "\n".join(lines) if lines else ""
        except Exception as exc:
            logger.debug("MemPalace recall unavailable: %s", type(exc).__name__)
            return ""

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "", messages=None) -> None:
        # Strictly no automatic filing. Built-in memory remains sole writer.
        return None

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        # No mutating MemPalace tool surface. Context-only recall.
        return []


def register(ctx) -> None:
    ctx.register_memory_provider(MemPalaceRecallProvider())
