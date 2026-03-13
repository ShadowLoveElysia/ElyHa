"""Prompt builder for HITL-first strong context management."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any

from elyha_core.utils.token_counter import TokenCounter


PROMPT_VERSION = "hitl_context_v1"

_SENTENCE_ENDINGS = set(".!?。！？\n")


@dataclass(slots=True)
class BuildInput:
    project_id: str
    node_id: str
    task_mode: str  # generate | correct
    token_budget: int
    system_spec: str = ""
    global_directives: Any = None
    world_state_snapshot: Any = None
    node_context: Any = None
    working_memory: str = ""
    rag_context: str = ""
    user_correction: str = ""
    recent_anchor: str = ""
    context_soft_min_chars: int = 3000
    context_soft_max_chars: int = 5000
    context_sentence_safe_expand_chars: int = 500
    context_soft_max_tokens: int = 1600
    strict_json_fence_output: bool = False
    tokenizer_model: str = ""
    context_compaction_enabled: bool = True
    context_compaction_trigger_ratio: int = 80
    context_compaction_keep_recent_chunks: int = 4
    context_compaction_group_chunks: int = 4
    context_compaction_chunk_chars: int = 1200


@dataclass(slots=True)
class PromptSectionInfo:
    name: str
    chars: int
    tokens: int


@dataclass(slots=True)
class PromptBundle:
    final_prompt: str
    sections: list[PromptSectionInfo] = field(default_factory=list)
    dropped_sections: list[dict[str, Any]] = field(default_factory=list)
    prompt_version: str = PROMPT_VERSION
    key_constraints: list[str] = field(default_factory=list)
    token_counter_backend: str = ""
    cache_monitor: dict[str, Any] = field(default_factory=dict)

    def sections_payload(self) -> list[dict[str, Any]]:
        return [
            {"name": item.name, "chars": item.chars, "tokens": item.tokens}
            for item in self.sections
        ]


@dataclass(slots=True)
class _Section:
    name: str
    text: str
    required: bool = False

    @property
    def chars(self) -> int:
        return len(self.text)

    @property
    def tokens(self) -> int:
        return max(1, len(self.text) // 4) if self.text else 0


class ContextAssembler:
    """Assemble bounded prompt context with deterministic trimming."""

    def __init__(self, token_counter: TokenCounter | None = None) -> None:
        self._token_counter = token_counter or TokenCounter()

    def build_generation_prompt(self, input_data: BuildInput) -> PromptBundle:
        return self._build_prompt(input_data, correction_mode=False)

    def build_correction_prompt(self, input_data: BuildInput) -> PromptBundle:
        return self._build_prompt(input_data, correction_mode=True)

    def _build_prompt(self, input_data: BuildInput, *, correction_mode: bool) -> PromptBundle:
        token_budget = max(200, int(input_data.token_budget))
        dropped: list[dict[str, Any]] = []
        key_constraints = self._key_constraints(correction_mode=correction_mode)
        model_hint = str(input_data.tokenizer_model or "").strip()
        token_backend = self._token_counter.backend(model_hint=model_hint)

        system_spec = self._normalize_system_spec(input_data)
        global_directives = self._normalize_global_directives(input_data.global_directives)
        world_state = self._normalize_world_state(input_data.world_state_snapshot)
        node_context = self._normalize_node_context(input_data.node_context)
        working_memory, wm_dropped = self._normalize_working_memory(input_data)
        dropped.extend(wm_dropped)
        rag_context = self._normalize_text(input_data.rag_context)
        user_correction = self._normalize_user_correction(input_data.user_correction)

        sections: dict[str, _Section] = {
            "SystemSpec": _Section("SystemSpec", system_spec, required=True),
            "GlobalDirectives": _Section("GlobalDirectives", global_directives, required=False),
            "WorldStateSnapshot": _Section("WorldStateSnapshot", world_state, required=True),
            "NodeContext": _Section("NodeContext", node_context, required=True),
            "WorkingMemoryRecent": _Section("WorkingMemoryRecent", working_memory, required=False),
            "LocalRAGContext": _Section("LocalRAGContext", rag_context, required=False),
        }
        if correction_mode and user_correction:
            sections["UserCorrection"] = _Section("UserCorrection", user_correction, required=True)

        def _section_tokens(name: str) -> int:
            section = sections[name]
            if not section.text:
                return 0
            return self._count_tokens(section.text, model_hint=model_hint)

        section_budgets = self._section_token_budgets(token_budget)
        sections["SystemSpec"] = self._trim_basic(
            sections["SystemSpec"],
            max_tokens=section_budgets["SystemSpec"],
            dropped=dropped,
            model_hint=model_hint,
        )
        sections["GlobalDirectives"] = self._trim_basic(
            sections["GlobalDirectives"],
            max_tokens=section_budgets["GlobalDirectives"],
            dropped=dropped,
            model_hint=model_hint,
        )
        sections["NodeContext"] = self._trim_basic(
            sections["NodeContext"],
            max_tokens=section_budgets["NodeContext"],
            dropped=dropped,
            model_hint=model_hint,
        )
        sections["LocalRAGContext"] = self._trim_basic(
            sections["LocalRAGContext"],
            max_tokens=section_budgets["LocalRAGContext"],
            dropped=dropped,
            model_hint=model_hint,
        )
        sections["WorkingMemoryRecent"] = self._trim_working_memory_by_tokens(
            sections["WorkingMemoryRecent"],
            max_tokens=section_budgets["WorkingMemoryRecent"],
            dropped=dropped,
            input_data=input_data,
            aggressive=False,
            model_hint=model_hint,
        )

        # Overflow handling: LocalRAGContext -> WorkingMemoryRecent, do not trim snapshot/correction.
        ordered_names = [
            "SystemSpec",
            "GlobalDirectives",
            "WorldStateSnapshot",
            "NodeContext",
            "WorkingMemoryRecent",
            "LocalRAGContext",
        ]
        if "UserCorrection" in sections:
            ordered_names.append("UserCorrection")

        def _total_tokens() -> int:
            return sum(_section_tokens(name) for name in ordered_names if sections[name].text)

        if _total_tokens() > token_budget and sections["LocalRAGContext"].text:
            reduce_to = max(0, _section_tokens("LocalRAGContext") - (_total_tokens() - token_budget))
            sections["LocalRAGContext"] = self._trim_basic(
                sections["LocalRAGContext"],
                max_tokens=reduce_to,
                dropped=dropped,
                model_hint=model_hint,
            )

        if _total_tokens() > token_budget and sections["WorkingMemoryRecent"].text:
            reduce_to = max(64, _section_tokens("WorkingMemoryRecent") - (_total_tokens() - token_budget))
            sections["WorkingMemoryRecent"] = self._trim_working_memory_by_tokens(
                sections["WorkingMemoryRecent"],
                max_tokens=reduce_to,
                dropped=dropped,
                input_data=input_data,
                aggressive=True,
                model_hint=model_hint,
            )

        # Emergency fallback if still overflowing due required sections.
        if _total_tokens() > token_budget:
            overflow = _total_tokens() - token_budget
            for name in ("GlobalDirectives", "SystemSpec", "NodeContext"):
                if overflow <= 0:
                    break
                if not sections[name].text:
                    continue
                target = max(32, _section_tokens(name) - overflow)
                sections[name] = self._trim_basic(
                    sections[name],
                    max_tokens=target,
                    dropped=dropped,
                    model_hint=model_hint,
                )
                overflow = _total_tokens() - token_budget

        lines: list[str] = []
        lines.append("[PriorityRules]")
        if correction_mode and "UserCorrection" in sections:
            lines.append("1) UserCorrection has highest priority and cannot be ignored.")
            lines.append("2) WorldStateSnapshot is factual truth when conflict exists.")
        else:
            lines.append("1) WorldStateSnapshot is factual truth when conflict exists.")
        lines.append("3) Follow GlobalDirectives and SystemSpec unless they conflict with higher priority.")
        lines.append("")
        for name in ordered_names:
            section = sections[name]
            if not section.text:
                continue
            lines.append(f"[{name}]")
            lines.append(section.text)
            lines.append("")

        if input_data.strict_json_fence_output:
            lines.append("[OutputContract]")
            lines.append("strict_json_fence_output=true")
            lines.append("Response must be and only be a single ```json ... ``` fenced block.")
            lines.append("")

        lines.append("[KeyConstraintsChecklist]")
        for index, item in enumerate(key_constraints, start=1):
            lines.append(f"{index}. {item}")
        final_prompt = "\n".join(lines).strip()

        section_infos = [
            PromptSectionInfo(
                name=name,
                chars=sections[name].chars,
                tokens=_section_tokens(name),
            )
            for name in ordered_names
            if sections[name].text
        ]
        return PromptBundle(
            final_prompt=final_prompt,
            sections=section_infos,
            dropped_sections=dropped,
            key_constraints=key_constraints,
            token_counter_backend=token_backend,
        )

    def _section_token_budgets(self, token_budget: int) -> dict[str, int]:
        system_global = max(20, int(token_budget * 0.15))
        return {
            "SystemSpec": max(10, int(system_global * 0.55)),
            "GlobalDirectives": max(10, system_global - int(system_global * 0.55)),
            "WorldStateSnapshot": max(20, int(token_budget * 0.20)),
            "NodeContext": max(20, int(token_budget * 0.15)),
            "WorkingMemoryRecent": max(40, int(token_budget * 0.30)),
            "LocalRAGContext": max(20, int(token_budget * 0.15)),
        }

    def _normalize_system_spec(self, input_data: BuildInput) -> str:
        blocks: list[str] = []
        spec = self._normalize_text(input_data.system_spec)
        if spec:
            blocks.append(spec)
        if input_data.strict_json_fence_output:
            blocks.append("strict_json_fence_output=true")
        return "\n\n".join(blocks).strip()

    def _normalize_global_directives(self, value: Any) -> str:
        if value is None:
            return ""
        directives: list[tuple[int, str]] = []
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    enabled = bool(item.get("enabled", True))
                    if not enabled:
                        continue
                    rule = str(item.get("rule") or item.get("text") or "").strip()
                    if not rule:
                        continue
                    priority = self._safe_int(item.get("priority"), fallback=100)
                    directives.append((priority, rule))
                else:
                    text = str(item).strip()
                    if text:
                        directives.append((100, text))
        elif isinstance(value, dict):
            for _, raw in value.items():
                text = str(raw).strip()
                if text:
                    directives.append((100, text))
        else:
            raw_text = str(value).strip()
            if raw_text:
                maybe_json = self._try_load_json(raw_text)
                if isinstance(maybe_json, list):
                    return self._normalize_global_directives(maybe_json)
                for line in raw_text.splitlines():
                    cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)、])\s*", "", line).strip()
                    if cleaned:
                        directives.append((100, cleaned))
        directives.sort(key=lambda item: (item[0], item[1]))
        if not directives:
            return ""
        lines = [f"{idx}. {text}" for idx, (_, text) in enumerate(directives, start=1)]
        return "\n".join(lines)

    def _normalize_world_state(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return ""
            maybe_json = self._try_load_json(text)
            if maybe_json is not None:
                value = maybe_json
            else:
                return text
        prefix = "If any context conflicts with this snapshot, this snapshot must win."
        try:
            payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
        except (TypeError, ValueError):
            payload = str(value)
        return f"{prefix}\n\n```json\n{payload}\n```".strip()

    def _normalize_node_context(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
        except (TypeError, ValueError):
            return str(value)

    def _normalize_working_memory(self, input_data: BuildInput) -> tuple[str, list[dict[str, Any]]]:
        dropped: list[dict[str, Any]] = []
        text = self._normalize_text(input_data.working_memory)
        if not text:
            return "", dropped

        anchor = self._normalize_text(input_data.recent_anchor)
        if not bool(input_data.context_compaction_enabled):
            return self._normalize_working_memory_legacy(input_data, anchor=anchor)

        token_limit = max(80, int(input_data.context_soft_max_tokens))
        model_hint = str(input_data.tokenizer_model or "").strip()
        trigger_ratio = min(100, max(50, int(input_data.context_compaction_trigger_ratio)))
        trigger_base = max(token_limit, int(input_data.token_budget))
        compaction_trigger_tokens = max(token_limit, int(trigger_base * trigger_ratio / 100))

        merged = text
        raw_tokens = self._count_tokens(merged, model_hint=model_hint)
        if raw_tokens >= compaction_trigger_tokens:
            compacted, compaction_info = self._compact_working_memory_append_only(
                merged,
                input_data=input_data,
            )
            if compacted != merged:
                merged = compacted
                dropped.append(compaction_info)

        if anchor:
            merged = f"{merged}\n\n[RecentReplyAndProposalSummary]\n{anchor}".strip()
        merged_tokens = self._count_tokens(merged, model_hint=model_hint)
        if merged_tokens > token_limit:
            if "[CompactedContext]" in merged and "[RecentRaw]" in merged:
                merged = self._clip_compacted_working_memory(
                    merged,
                    token_limit=token_limit,
                    expand_chars=max(0, int(input_data.context_sentence_safe_expand_chars)),
                    model_hint=model_hint,
                )
            else:
                merged = self._clip_text_by_token_limit(
                    merged,
                    token_limit=token_limit,
                    sentence_safe=True,
                    expand_chars=max(0, int(input_data.context_sentence_safe_expand_chars)),
                    model_hint=model_hint,
                )
            dropped.append(
                {
                    "section": "WorkingMemoryRecent",
                    "reason": "token_soft_limit",
                    "detail": f"token_limit={token_limit}",
                }
            )
        return merged, dropped

    def _normalize_working_memory_legacy(
        self,
        input_data: BuildInput,
        *,
        anchor: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        dropped: list[dict[str, Any]] = []
        text = self._normalize_text(input_data.working_memory)
        if not text:
            return "", dropped
        model_hint = str(input_data.tokenizer_model or "").strip()
        soft_min = max(200, int(input_data.context_soft_min_chars))
        soft_max = max(soft_min, int(input_data.context_soft_max_chars))
        expand = max(0, int(input_data.context_sentence_safe_expand_chars))
        token_limit = max(80, int(input_data.context_soft_max_tokens))

        if len(text) <= soft_max:
            merged = text
            if anchor:
                merged = f"{merged}\n\n[RecentReplyAndProposalSummary]\n{anchor}".strip()
            if self._count_tokens(merged, model_hint=model_hint) > token_limit:
                merged = self._clip_text_by_token_limit(
                    merged,
                    token_limit=token_limit,
                    sentence_safe=True,
                    expand_chars=expand,
                    model_hint=model_hint,
                )
                dropped.append(
                    {
                        "section": "WorkingMemoryRecent",
                        "reason": "token_soft_limit",
                        "detail": "trimmed_to_token_limit",
                    }
                )
            return merged, dropped

        tail = self._clip_tail_sentence_safe(text, target_chars=soft_max, expand_chars=expand)
        head = text[: max(0, len(text) - len(tail))].strip()
        summary = self._summarize_head(head)
        merged = f"[HeadSummary]\n{summary}\n\n[RecentRaw]\n{tail}".strip()
        if anchor:
            merged = f"{merged}\n\n[RecentReplyAndProposalSummary]\n{anchor}".strip()
        dropped.append(
            {
                "section": "WorkingMemoryRecent",
                "reason": "char_soft_limit",
                "detail": f"head_summarized_to_keep_recent_raw<=~{soft_max}",
            }
        )

        if self._count_tokens(merged, model_hint=model_hint) > token_limit:
            merged = self._clip_text_by_token_limit(
                merged,
                token_limit=max(64, token_limit),
                sentence_safe=True,
                expand_chars=expand,
                model_hint=model_hint,
            )
            dropped.append(
                {
                    "section": "WorkingMemoryRecent",
                    "reason": "token_soft_limit",
                    "detail": f"token_limit={token_limit}",
                }
            )
        return merged, dropped

    def _compact_working_memory_append_only(
        self,
        text: str,
        *,
        input_data: BuildInput,
    ) -> tuple[str, dict[str, Any]]:
        cleaned = self._normalize_text(text)
        if not cleaned:
            return "", {
                "section": "WorkingMemoryRecent",
                "reason": "append_only_compaction",
                "detail": "empty_input",
            }
        keep_recent = max(1, int(input_data.context_compaction_keep_recent_chunks))
        group_size = max(1, int(input_data.context_compaction_group_chunks))
        chunk_chars = max(240, int(input_data.context_compaction_chunk_chars))
        chunks = self._chunk_text_for_compaction(cleaned, target_chars=chunk_chars)
        if len(chunks) <= keep_recent + group_size:
            return cleaned, {
                "section": "WorkingMemoryRecent",
                "reason": "append_only_compaction",
                "detail": "append_phase_no_full_group",
            }

        compactable_count = max(0, len(chunks) - keep_recent)
        full_group_chunk_count = (compactable_count // group_size) * group_size
        if full_group_chunk_count <= 0:
            return cleaned, {
                "section": "WorkingMemoryRecent",
                "reason": "append_only_compaction",
                "detail": "append_phase_no_full_group",
            }

        compacted_chunks = chunks[:full_group_chunk_count]
        recent_chunks = chunks[full_group_chunk_count:]
        group_total = full_group_chunk_count // group_size
        group_summaries: list[str] = []
        for index in range(group_total):
            start = index * group_size
            end = start + group_size
            group_text = "\n\n".join(compacted_chunks[start:end]).strip()
            summary = self._summarize_head(group_text)
            group_summaries.append(f"{index + 1}. {summary}")

        lines: list[str] = [
            "[CompactedContext]",
            "Working memory uses append-only staircase compaction.",
            *group_summaries,
            "",
        ]
        recent_block = "\n\n".join(item for item in recent_chunks if item.strip()).strip()
        if recent_block:
            lines.append("[RecentRaw]")
            lines.append(recent_block)

        compacted = "\n".join(lines).strip()
        detail = (
            f"groups={group_total},group_size={group_size},"
            f"compacted_chunks={full_group_chunk_count},recent_chunks={len(recent_chunks)}"
        )
        return compacted, {
            "section": "WorkingMemoryRecent",
            "reason": "append_only_compaction",
            "detail": detail,
        }

    def _chunk_text_for_compaction(self, text: str, *, target_chars: int) -> list[str]:
        cleaned = self._normalize_text(text)
        if not cleaned:
            return []
        segments = [
            part.strip()
            for part in re.split(r"(?<=[。！？.!?\n])\s*", cleaned)
            if part and part.strip()
        ]
        if not segments:
            segments = [cleaned]

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        target = max(240, int(target_chars))
        for segment in segments:
            segment_len = len(segment)
            projected = current_len + segment_len + (1 if current else 0)
            if current and projected > target:
                chunks.append(" ".join(current).strip())
                current = [segment]
                current_len = segment_len
            else:
                current.append(segment)
                current_len = projected
        if current:
            chunks.append(" ".join(current).strip())
        return [item for item in chunks if item]

    def _normalize_user_correction(self, value: Any) -> str:
        text = self._normalize_text(value)
        if not text:
            return ""
        return (
            "Highest priority instruction from user correction. "
            "Only revise requested scope and do not ignore explicit edits.\n\n"
            f"{text}"
        )

    def _trim_basic(
        self,
        section: _Section,
        *,
        max_tokens: int,
        dropped: list[dict[str, Any]],
        model_hint: str,
    ) -> _Section:
        if not section.text:
            return section
        if max_tokens <= 0:
            dropped.append({"section": section.name, "reason": "budget_zero", "detail": "dropped"})
            return _Section(name=section.name, text="", required=section.required)
        source_tokens = self._count_tokens(section.text, model_hint=model_hint)
        if source_tokens <= max_tokens:
            return section
        trimmed = self._clip_head_text_by_token_limit(
            section.text,
            token_limit=max_tokens,
            model_hint=model_hint,
        )
        trimmed_tokens = self._count_tokens(trimmed, model_hint=model_hint)
        dropped.append(
            {
                "section": section.name,
                "reason": "budget_trim",
                "detail": f"tokens:{source_tokens}->{trimmed_tokens}",
            }
        )
        return _Section(name=section.name, text=trimmed, required=section.required)

    def _trim_working_memory_by_tokens(
        self,
        section: _Section,
        *,
        max_tokens: int,
        dropped: list[dict[str, Any]],
        input_data: BuildInput,
        aggressive: bool,
        model_hint: str,
    ) -> _Section:
        if not section.text:
            return section
        if max_tokens <= 0:
            dropped.append({"section": section.name, "reason": "budget_zero", "detail": "dropped"})
            return _Section(name=section.name, text="", required=section.required)
        source_tokens = self._count_tokens(section.text, model_hint=model_hint)
        if source_tokens <= max_tokens:
            return section
        expand = max(0, int(input_data.context_sentence_safe_expand_chars))
        if "[CompactedContext]" in section.text and "[RecentRaw]" in section.text:
            clipped = self._clip_compacted_working_memory(
                section.text,
                token_limit=max_tokens,
                expand_chars=0 if aggressive else expand,
                model_hint=model_hint,
            )
        else:
            clipped = self._clip_text_by_token_limit(
                section.text,
                token_limit=max_tokens,
                sentence_safe=True,
                expand_chars=0 if aggressive else expand,
                model_hint=model_hint,
            )
        clipped_tokens = self._count_tokens(clipped, model_hint=model_hint)
        dropped.append(
            {
                "section": section.name,
                "reason": "budget_trim",
                "detail": f"tokens:{source_tokens}->{clipped_tokens}",
            }
        )
        return _Section(name=section.name, text=clipped, required=section.required)

    def _clip_text_by_token_limit(
        self,
        text: str,
        *,
        token_limit: int,
        sentence_safe: bool,
        expand_chars: int,
        model_hint: str,
    ) -> str:
        if not text:
            return ""
        if token_limit <= 0:
            return ""
        source_tokens = self._count_tokens(text, model_hint=model_hint)
        if source_tokens <= token_limit:
            return text
        char_limit = self._max_tail_chars_for_tokens(
            text,
            token_limit=token_limit,
            model_hint=model_hint,
        )
        if char_limit >= len(text):
            return text
        if not sentence_safe:
            return text[-char_limit:].lstrip()
        tail = self._clip_tail_sentence_safe(text, target_chars=char_limit, expand_chars=expand_chars)
        if self._count_tokens(tail, model_hint=model_hint) <= token_limit:
            return tail if len(tail) <= len(text) else text
        return self._clip_text_by_token_limit(
            tail,
            token_limit=token_limit,
            sentence_safe=False,
            expand_chars=0,
            model_hint=model_hint,
        )

    def _clip_compacted_working_memory(
        self,
        text: str,
        *,
        token_limit: int,
        expand_chars: int,
        model_hint: str,
    ) -> str:
        marker = "[RecentRaw]"
        idx = text.find(marker)
        if idx < 0:
            return self._clip_text_by_token_limit(
                text,
                token_limit=token_limit,
                sentence_safe=True,
                expand_chars=expand_chars,
                model_hint=model_hint,
            )
        prefix = text[: idx + len(marker)].rstrip()
        recent_raw = text[idx + len(marker) :].strip()
        prefix_tokens = self._count_tokens(prefix, model_hint=model_hint)
        if prefix_tokens >= token_limit:
            return self._clip_head_text_by_token_limit(
                prefix,
                token_limit=token_limit,
                model_hint=model_hint,
            )
        remaining = max(1, token_limit - prefix_tokens)
        if not recent_raw:
            return prefix
        clipped_recent = self._clip_text_by_token_limit(
            recent_raw,
            token_limit=remaining,
            sentence_safe=True,
            expand_chars=expand_chars,
            model_hint=model_hint,
        )
        return f"{prefix}\n{clipped_recent}".strip()

    def _clip_head_text_by_token_limit(self, text: str, *, token_limit: int, model_hint: str) -> str:
        if not text:
            return ""
        if token_limit <= 0:
            return ""
        source_tokens = self._count_tokens(text, model_hint=model_hint)
        if source_tokens <= token_limit:
            return text
        char_limit = self._max_head_chars_for_tokens(
            text,
            token_limit=token_limit,
            model_hint=model_hint,
        )
        clipped = text[:char_limit].rstrip()
        if char_limit < len(text):
            clipped = f"{clipped}..."
        return clipped

    def _max_head_chars_for_tokens(self, text: str, *, token_limit: int, model_hint: str) -> int:
        lo = 1
        hi = len(text)
        best = 1
        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = text[:mid]
            if self._count_tokens(candidate, model_hint=model_hint) <= token_limit:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return max(1, best)

    def _max_tail_chars_for_tokens(self, text: str, *, token_limit: int, model_hint: str) -> int:
        lo = 1
        hi = len(text)
        best = 1
        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = text[-mid:]
            if self._count_tokens(candidate, model_hint=model_hint) <= token_limit:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return max(1, best)

    def _clip_tail_sentence_safe(self, text: str, *, target_chars: int, expand_chars: int) -> str:
        if len(text) <= target_chars:
            return text
        desired_start = max(0, len(text) - target_chars)
        lo = max(0, desired_start - max(0, expand_chars))
        hi = min(len(text), desired_start + max(0, expand_chars))

        prev_boundary = self._find_prev_boundary(text, desired_start, lo)
        if prev_boundary is not None:
            return text[prev_boundary:].lstrip()
        next_boundary = self._find_next_boundary(text, desired_start, hi)
        if next_boundary is not None:
            return text[next_boundary:].lstrip()
        return text[desired_start:].lstrip()

    def _find_prev_boundary(self, text: str, start: int, stop: int) -> int | None:
        idx = start
        while idx > stop:
            idx -= 1
            if text[idx] in _SENTENCE_ENDINGS:
                return min(len(text), idx + 1)
        return None

    def _find_next_boundary(self, text: str, start: int, stop: int) -> int | None:
        idx = start
        while idx < stop:
            if text[idx] in _SENTENCE_ENDINGS:
                return min(len(text), idx + 1)
            idx += 1
        return None

    def _summarize_head(self, text: str) -> str:
        cleaned = self._normalize_text(text)
        if not cleaned:
            return "(empty)"
        sentences = re.split(r"(?<=[。！？.!?])\s+", cleaned)
        picked: list[str] = []
        for sentence in sentences:
            candidate = sentence.strip()
            if not candidate:
                continue
            picked.append(candidate)
            if len(" ".join(picked)) >= 360:
                break
        if not picked:
            picked = [cleaned[:360]]
        summary = " ".join(picked).strip()
        if len(summary) > 420:
            summary = summary[:420].rstrip() + "..."
        return summary

    def _normalize_text(self, value: Any) -> str:
        text = str(value or "")
        return text.replace("\r\n", "\n").replace("\r", "\n").strip()

    def _safe_int(self, value: Any, *, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    def _estimate_tokens(self, text: str) -> int:
        return self._count_tokens(text, model_hint=self._token_counter.default_model_hint())

    def _count_tokens(self, text: str, *, model_hint: str) -> int:
        return self._token_counter.count(text, model_hint=model_hint)

    def _try_load_json(self, text: str) -> Any:
        try:
            return json.loads(text)
        except Exception:
            return None

    def _key_constraints(self, *, correction_mode: bool) -> list[str]:
        constraints = [
            "WorldStateSnapshot overrides conflicting context.",
            "Do not invent facts that contradict provided state.",
        ]
        if correction_mode:
            constraints.insert(0, "Apply UserCorrection with highest priority in requested scope.")
        return constraints
