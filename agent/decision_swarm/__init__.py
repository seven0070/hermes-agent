"""Opt-in local, advisory turn routing. Never an authorization mechanism."""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
HEADS = {
    'intent': {'lookup', 'research', 'coding', 'conversation'},
    'complexity': {'simple', 'complex'},
    'tool_need': {'yes', 'no'},
    'tier': {'fast', 'primary'},
}
_DATA = Path(__file__).parent / 'seed.tsv'
_MODELS = Path(__file__).parent / 'models'
_cache: dict[str, Any] = {}


def classify(text: str, model_dir: str | Path | None = None) -> dict[str, dict[str, float | str]] | None:
    """Four independent heads over the SAME bounded input; no side effects.

    Probabilities are raw fastText scores, not Jev-style calibrated confidence.
    """
    try:
        import fasttext
        directory = Path(model_dir or _MODELS).expanduser().resolve()
        if not text.strip() or len(text) > 4000 or not directory.is_dir():
            return None
        result = {}
        for name in HEADS:
            path = directory / f'{name}.bin'
            if not path.is_file():
                return None
            key = str(path)
            stamp = (path.stat().st_mtime_ns, path.stat().st_size)
            cached = _cache.get(key)
            if cached is None or cached[0] != stamp:
                cached = (stamp, fasttext.load_model(key))
                _cache[key] = cached
            labels, probabilities = cached[1].predict(re.sub(r'\s+', ' ', text.strip()), k=-1)
            scores = {label.removeprefix('__label__'): float(prob) for label, prob in zip(labels, probabilities)}
            if set(scores) != HEADS[name]:
                return None
            label = max(scores, key=scores.get)
            result[name] = {'label': label, 'probability': scores[label], 'margin': scores[label] - max((p for k, p in scores.items() if k != label), default=0.0)}
        return result
    except Exception as exc:
        logger.debug('local decision classification unavailable: %s', type(exc).__name__)
        return None


def choose_tier(text: str, config: dict | None, *, explicit_model: bool = False) -> str:
    """Return fast or primary. Only primary is safe on every uncertainty path."""
    if not isinstance(config, dict) or config.get('enabled') is not True or explicit_model:
        return 'primary'
    # Do not classify control commands, links, messages with likely private
    # account details, or long/ambiguous requests. These are not seed tasks.
    if (not isinstance(text, str) or len(text) > 400 or chr(10) in text
            or re.search(r'https?://|\b\S+@\S+\.\S+\b|\b(?:send|share|book|buy|pay|delete|update|change|schedule|remind)\b', text, re.I)
            or text.lstrip().startswith('/')):
        return 'primary'
    fast_model = config.get('fast_model')
    if not isinstance(fast_model, str) or not fast_model.strip():
        return 'primary'
    try:
        started = time.monotonic()
        decisions = classify(text, config.get('model_dir'))
        # This is an after-call budget, not a hard timeout (native inference
        # is synchronous). Operational latency must be benchmarked on Windows.
        if time.monotonic() - started > 0.25 or decisions is None:
            return 'primary'
        # A cheap route is only permitted on unanimous, high-margin evidence.
        # Threshold is conservative, provisional, and must be tuned on local evals.
        threshold = config.get('threshold', 0.85)
        if isinstance(threshold, bool) or not isinstance(threshold, (float, int)) or not 0.8 <= threshold <= 0.99:
            return 'primary'
        if any(d['probability'] < threshold or d['margin'] < 0.5 for d in decisions.values()):
            return 'primary'
        if decisions['complexity']['label'] != 'simple' or decisions['tier']['label'] != 'fast':
            return 'primary'
        if decisions['tool_need']['label'] != 'no' or decisions['intent']['label'] not in {'lookup', 'conversation'}:
            return 'primary'
        return 'fast'
    except Exception:
        return 'primary'


def train(dataset: Path, output: Path) -> None:
    """Train four local classifiers from TSV: text, intent, complexity, tool_need, tier.

    Run this deliberately with reviewed examples. It never reads chat history.
    """
    import csv
    import tempfile
    import fasttext
    rows = list(csv.DictReader(dataset.open(encoding='utf-8', newline=''), delimiter='\t'))
    if len(rows) < 12:
        raise ValueError('At least 12 labeled examples required')
    for row in rows:
        if any(row.get(head) not in labels for head, labels in HEADS.items()):
            raise ValueError('Unknown or missing label')
        if not row.get('text', '').strip() or len(row['text']) > 4000:
            raise ValueError('Missing or overlong text')
    output.mkdir(parents=True, exist_ok=True)
    for head in HEADS:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', suffix='.txt', delete=False) as file:
            path = Path(file.name)
            for row in rows:
                file.write(f"__label__{row[head]} {re.sub(chr(10), ' ', row['text'])}\n")
        try:
            model = fasttext.train_supervised(str(path), epoch=30, lr=0.5, wordNgrams=2, dim=16, bucket=2000, minCount=1, thread=1, verbose=0)
            model.save_model(str(output / f'{head}.bin'))
        finally:
            path.unlink(missing_ok=True)
