from __future__ import annotations

import argparse
from pathlib import Path


def build_parser(*, internal: bool = False) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run real InfiniCrafter LLM generation while hard-blocking every image backend call."
    )
    parser.add_argument("--project", type=Path, help="Authoritative InfiniCrafterLocal worktree.")
    parser.add_argument("--output", type=Path, help="Private trace directory; required for --run, untouched by preflight.")
    parser.add_argument("--cases", help="Distinct comma-separated case IDs; default is the named Live10/Live20 panel.")
    parser.add_argument(
        "--cases-file",
        type=Path,
        help="Custom JSON cases with {case,itemA,itemB} parent identities.",
    )
    parser.add_argument(
        "--runtime-dump", type=Path,
        help="Parent item JSONL; defaults to the bundled exact Terraria fixture in toolbox/fixtures.",
    )
    parser.add_argument("--expected-case-count", type=int, help="Require the selected case count before network.")
    parser.add_argument("--transport-retries", type=int, default=0, help="Explicit retries per case for confirmed network failures only.")
    parser.add_argument(
        "--transport-retry-delay-seconds", type=int, default=60,
        help="Minimum wait after a network failure before retrying that case; at least 60 seconds.",
    )
    parser.add_argument("--expected-provider", help="Fail before network if the configured provider differs.")
    parser.add_argument("--expected-model", help="Fail before network or per request if the exact model differs.")
    parser.add_argument("--expected-base-url", help="Require the exact configured OpenAI-compatible endpoint.")
    parser.add_argument("--expected-api-mode", help="Require the exact configured LLM API mode.")
    parser.add_argument("--expected-response-format", help="Require the exact configured structured-output mode.")
    parser.add_argument("--expected-temperature", type=float, help="Require this temperature in Author and Visual director requests.")
    parser.add_argument("--expected-vfx-temperature", type=float, help="Require the configured VFX director temperature without changing it.")
    parser.add_argument(
        "--expected-repair-temperature",
        type=float,
        help="Require this temperature in Gameplay, Visual, and VFX Repair requests; defaults to --expected-temperature.",
    )
    parser.add_argument("--expected-max-tokens", type=int, help="Require this answer-token budget in Author and Gameplay Repair requests.")
    parser.add_argument(
        "--expected-visual-max-tokens", type=int,
        help="Require this answer-token budget in Visual Director/Repair requests; defaults to --expected-max-tokens.",
    )
    parser.add_argument(
        "--expected-vfx-max-tokens", type=int,
        help="Require this answer-token budget in VFX Director/Repair requests; defaults to --expected-max-tokens.",
    )
    parser.add_argument("--expected-reasoning-effort", help="Require this provider reasoning_effort in every LLM request.")
    parser.add_argument("--expected-head", help="Require this clean Git HEAD before starting the campaign.")
    parser.add_argument("--require-no-fallback", action="store_true", help="Reject fallback and enabled pool routes.")
    parser.add_argument(
        "--require-zero-transport-retries",
        action="store_true",
        help="Fail if any successful logical LLM call needed a hidden low-level HTTP retry.",
    )
    parser.add_argument("--min-first-author", type=int, default=0, help="Required first-Author successes without Repair or earlier case retries; default 0 (no quality threshold).")
    parser.add_argument("--parallel-crafts", type=int, default=3, help="Concurrent craft workers within 1..8; default 3.")
    parser.add_argument("--preflight-only", action="store_true", help="Read-only config/case/source admission (the default); no runtime imports or network.")
    if internal:
        parser.add_argument("--panel", choices=("live10", "live20"), default="live20")
    parser.add_argument("--config", type=Path, help="Private env file; never committed. Environment takes precedence.")
    parser.add_argument("--run", action="store_true", help="Explicitly authorize text inference; default is read-only preflight.")
    return parser
