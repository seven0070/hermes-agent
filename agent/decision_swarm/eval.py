"""Evaluate held-out, manually labeled TSV and cold/warm decision time."""
from __future__ import annotations
import argparse
import csv
import statistics
import time
from pathlib import Path
from . import HEADS, classify


def evaluate(dataset: Path, model_dir: Path):
    rows = list(csv.DictReader(dataset.open(encoding='utf-8', newline=''), delimiter='\t'))
    if not rows:
        raise ValueError('Empty eval set')
    correct = dict.fromkeys(HEADS, 0)
    misses = 0
    times = []
    cold_ms = None
    for row in rows:
        start = time.perf_counter()
        result = classify(row['text'], model_dir)
        elapsed = (time.perf_counter() - start) * 1000
        if cold_ms is None:
            cold_ms = elapsed
        times.append(elapsed)
        if result is None:
            misses += 1
            continue
        for head in HEADS:
            correct[head] += result[head]['label'] == row[head]
    warm = sorted(times[1:]) or times
    return {'count': len(rows), 'abstentions': misses,
            'accuracy': {head: round(hits / len(rows), 3) for head, hits in correct.items()},
            'latency_ms': {'cold': round(cold_ms, 2), 'warm_median': round(statistics.median(warm), 2),
                           'warm_p95': round(warm[min(len(warm)-1, int(.95*len(warm)))], 2)}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, required=True, help='Held-out labeled TSV; do not use training set')
    parser.add_argument('--models', type=Path, default=Path(__file__).parent / 'models')
    args = parser.parse_args()
    print(evaluate(args.data, args.models))
