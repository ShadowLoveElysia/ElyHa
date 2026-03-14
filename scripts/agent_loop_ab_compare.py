#!/usr/bin/env python3
"""Compare two agent-loop thread runs on token/call/read metrics."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from elyha_core.storage.repository import SQLiteRepository
from elyha_core.storage.sqlite_store import SQLiteStore


@dataclass(slots=True)
class ThreadStats:
    thread_id: str
    round_count: int
    tool_call_count: int
    prompt_tokens: int
    completion_tokens: int
    total_read_chars: int
    tool_error_count: int
    cache_hit_count: int
    proposal_created_count: int

    @property
    def total_tokens(self) -> int:
        return int(self.prompt_tokens) + int(self.completion_tokens)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _collect_stats(repository: SQLiteRepository, thread_id: str) -> ThreadStats:
    rounds = repository.list_agent_loop_rounds(thread_id)
    calls = repository.list_agent_tool_calls(thread_id)
    metrics_rows = repository.list_agent_loop_metrics(thread_id)
    prompt_tokens = sum(_safe_int(item.get("prompt_tokens")) for item in rounds)
    completion_tokens = sum(_safe_int(item.get("completion_tokens")) for item in rounds)
    total_read_chars = 0
    tool_error_count = 0
    cache_hit_count = 0
    proposal_created_count = 0
    for call in calls:
        meta = call.get("result_meta")
        if not isinstance(meta, dict):
            meta = {}
        total_read_chars += _safe_int(meta.get("read_chars"))
        if not bool(meta.get("ok", False)):
            tool_error_count += 1
        if bool(meta.get("cache_hit", False)):
            cache_hit_count += 1
        if bool(meta.get("proposal_created", False)):
            proposal_created_count += 1

    # Prefer persisted aggregate metrics if present.
    if metrics_rows:
        merged = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_read_chars": 0,
            "tool_error_count": 0,
            "cache_hit_count": 0,
            "proposal_created_count": 0,
        }
        for row in metrics_rows:
            payload = row.get("metrics")
            if not isinstance(payload, dict):
                payload = {}
            merged["prompt_tokens"] += _safe_int(payload.get("prompt_tokens"))
            merged["completion_tokens"] += _safe_int(payload.get("completion_tokens"))
            merged["total_read_chars"] += _safe_int(payload.get("total_read_chars"))
            merged["tool_error_count"] += _safe_int(payload.get("tool_error_count"))
            merged["cache_hit_count"] += _safe_int(payload.get("cache_hit_count"))
            merged["proposal_created_count"] += _safe_int(payload.get("proposal_created_count"))
        prompt_tokens = max(prompt_tokens, merged["prompt_tokens"])
        completion_tokens = max(completion_tokens, merged["completion_tokens"])
        total_read_chars = max(total_read_chars, merged["total_read_chars"])
        tool_error_count = max(tool_error_count, merged["tool_error_count"])
        cache_hit_count = max(cache_hit_count, merged["cache_hit_count"])
        proposal_created_count = max(proposal_created_count, merged["proposal_created_count"])

    return ThreadStats(
        thread_id=thread_id,
        round_count=len(rounds),
        tool_call_count=len(calls),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_read_chars=total_read_chars,
        tool_error_count=tool_error_count,
        cache_hit_count=cache_hit_count,
        proposal_created_count=proposal_created_count,
    )


def _delta_percent(baseline: int, candidate: int) -> str:
    if baseline <= 0:
        return "n/a"
    delta = ((candidate - baseline) / baseline) * 100.0
    return f"{delta:+.2f}%"


def _render_report(baseline: ThreadStats, candidate: ThreadStats) -> str:
    lines: list[str] = []
    lines.append(f"Baseline thread: {baseline.thread_id}")
    lines.append(f"Candidate thread: {candidate.thread_id}")
    lines.append("")
    lines.append("| Metric | Baseline | Candidate | Delta |")
    lines.append("|---|---:|---:|---:|")
    rows = [
        ("Rounds", baseline.round_count, candidate.round_count),
        ("Tool calls", baseline.tool_call_count, candidate.tool_call_count),
        ("Prompt tokens", baseline.prompt_tokens, candidate.prompt_tokens),
        ("Completion tokens", baseline.completion_tokens, candidate.completion_tokens),
        ("Total tokens", baseline.total_tokens, candidate.total_tokens),
        ("Read chars", baseline.total_read_chars, candidate.total_read_chars),
        ("Tool errors", baseline.tool_error_count, candidate.tool_error_count),
        ("Cache hits", baseline.cache_hit_count, candidate.cache_hit_count),
        ("Proposals created", baseline.proposal_created_count, candidate.proposal_created_count),
    ]
    for name, base_value, candidate_value in rows:
        lines.append(
            f"| {name} | {base_value} | {candidate_value} | {_delta_percent(base_value, candidate_value)} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two thread-level agent-loop runs.")
    parser.add_argument("--db", required=True, help="Path to SQLite database, e.g. data/elyha.db")
    parser.add_argument("--baseline-thread", required=True, help="Baseline thread_id")
    parser.add_argument("--candidate-thread", required=True, help="Candidate thread_id")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser().resolve()
    repository = SQLiteRepository(SQLiteStore(db_path))
    baseline = _collect_stats(repository, str(args.baseline_thread))
    candidate = _collect_stats(repository, str(args.candidate_thread))
    print(_render_report(baseline, candidate))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
