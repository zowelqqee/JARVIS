#!/usr/bin/env python3
"""Generate raw Russian Piper samples for A/B listening."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from voice.tts_ab_samples import (  # noqa: E402
    DEFAULT_RU_SAMPLE_PHRASES,
    default_ab_output_dir,
    default_piper_runtime_root,
    discover_ru_piper_candidates,
    render_ru_ab_samples,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate raw Russian Piper WAV samples for A/B voice selection.",
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=default_piper_runtime_root(ROOT_DIR),
        help="Piper runtime root. Defaults to repo-local tmp/runtime/piper.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_ab_output_dir(ROOT_DIR),
        help="Output directory for WAV samples and manifest.json.",
    )
    parser.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="Candidate key to render, for example denis, ruslan, dmitri. Can be repeated.",
    )
    parser.add_argument(
        "--phrase",
        action="append",
        default=[],
        help="Sample phrase to render. Can be repeated. Defaults to built-in Russian QA phrases.",
    )
    parser.add_argument(
        "--piper-binary",
        default="",
        help="Optional explicit Piper binary path.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="Per-sample Piper timeout in seconds.",
    )
    parser.add_argument(
        "--list-candidates",
        action="store_true",
        help="List discovered Russian candidates without rendering WAV files.",
    )
    args = parser.parse_args(argv)

    if args.list_candidates:
        for candidate in discover_ru_piper_candidates(args.runtime_root):
            print(f"{candidate.key}: {candidate.display_name} -> {candidate.model_path}")
        return 0

    phrases = tuple(args.phrase) if args.phrase else DEFAULT_RU_SAMPLE_PHRASES
    try:
        result = render_ru_ab_samples(
            runtime_root=args.runtime_root,
            output_dir=args.output_dir,
            phrases=phrases,
            candidate_keys=args.candidate,
            piper_binary=args.piper_binary or None,
            timeout_seconds=args.timeout,
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"output dir: {result.output_dir}")
    print(f"manifest: {result.manifest_path}")
    print("candidates:")
    for candidate in result.candidates:
        print(f"- {candidate.key}: {candidate.display_name}")
    failed = [sample for sample in result.results if not sample.ok]
    print(f"samples: {len(result.results)} rendered, {len(failed)} failed")
    for sample in failed:
        print(
            f"failed: {sample.candidate_key}/{sample.phrase_index:02d}: {sample.error or 'unknown error'}",
            file=sys.stderr,
        )
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
