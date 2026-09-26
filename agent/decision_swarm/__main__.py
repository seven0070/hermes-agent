from . import train, _DATA, _MODELS
import argparse
from pathlib import Path
parser = argparse.ArgumentParser(description='Train local decision heads from reviewed TSV examples')
parser.add_argument('--data', type=Path, default=_DATA)
parser.add_argument('--output', type=Path, default=_MODELS)
args = parser.parse_args()
train(args.data, args.output)
