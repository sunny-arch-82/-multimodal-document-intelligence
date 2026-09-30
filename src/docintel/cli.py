import argparse
import json
from pathlib import Path
from .pipeline import process
from .evaluation import evaluate

def main():
    parser = argparse.ArgumentParser(description="DocIntel local document intelligence")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("process")
    p.add_argument("file", type=Path)
    p.add_argument("--backend", choices=["rules", "local_vlm"], default="rules")
    p.add_argument("--output-dir", type=Path, default=Path("outputs"))
    e = commands.add_parser("evaluate")
    e.add_argument("--manifest", type=Path, default=Path("evals/manifest.json"))
    e.add_argument("--backend", choices=["rules", "local_vlm"], default="rules")
    e.add_argument("--output", type=Path, default=Path("outputs/evaluation.json"))
    args = parser.parse_args()
    try:
        if args.command == "process":
            result = process(args.file.name, args.file.read_bytes(), args.backend, args.output_dir)
            print(result.model_dump_json(indent=2))
        else:
            report = evaluate(args.manifest, args.backend)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"docintel: {exc}\n")
