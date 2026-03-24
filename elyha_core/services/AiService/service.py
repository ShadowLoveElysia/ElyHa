"""AI generation/review orchestration with task tracking."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import TYPE_CHECKING, Any, NoReturn, cast

from elyha_core.adapters.llm_adapter import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    create_llm_adapter,
)
from elyha_core.i18n import tr
from elyha_core.llm_presets import LLMPreset, preset_to_platform_config
from elyha_core.models.task import Task, TaskStatus
from elyha_core.services.context_assembler import (
    BuildInput,
    ContextAssembler,
    PromptBundle,
)
from elyha_core.services.context_service import ContextPack, ContextService
from elyha_core.services.graph_service import GraphService
from elyha_core.services.prompt_template_service import PromptTemplateService
from elyha_core.services.readable_content_tool_service import ReadableContentToolService
from elyha_core.services.Tools import ToolService
from elyha_core.services.validation_service import ValidationService
from elyha_core.storage.repository import SQLiteRepository
from elyha_core.utils.clock import utc_now
from elyha_core.utils.ids import generate_id
from elyha_core.utils.text_splitter import split_text_by_chars
from langgraph.graph import END, StateGraph

from .types import (
    BranchOption,
    ChapterDraftResult,
    ChatAssistResult,
    ClarificationQuestionResult,
    GenerateResult,
    OutlineDetailNode,
    OutlineDetailNodesResult,
    OutlineGuideResult,
    ReviewReport,
    WorkflowClarifyResult,
    WorkflowDocsDraftResult,
    WorkflowState,
    WorkflowSyncResult,
)
from .mixins import (
    AIServiceGenerationMixin,
    AIServicePromptMixin,
    AIServiceRuntimeMixin,
    AIServiceStateSyncMixin,
    AIServiceToolLoopMixin,
)

if TYPE_CHECKING:
    from elyha_core.services.setting_proposal_service import SettingProposalService
    from elyha_core.services.state_service import StateService

_STRICT_JSON_FENCE_PATTERN = re.compile(
    r"^\s*```json\s*([\s\S]*?)\s*```\s*$",
    flags=re.IGNORECASE,
)

_GUIDE_DOC_LABELS = {
    "constitution_markdown": "constitution",
    "clarify_markdown": "clarify",
    "specification_markdown": "specification",
    "plan_markdown": "plan",
}
_GUIDE_DOC_SLOTS = tuple(_GUIDE_DOC_LABELS.keys())
_GUIDE_DOC_ALIASES = {
    "constitution": "constitution_markdown",
    "constitution_markdown": "constitution_markdown",
    "clarify": "clarify_markdown",
    "clarify_markdown": "clarify_markdown",
    "specification": "specification_markdown",
    "specification_markdown": "specification_markdown",
    "plan": "plan_markdown",
    "plan_markdown": "plan_markdown",
}

class AIService(
    AIServiceGenerationMixin,
    AIServiceStateSyncMixin,
    AIServicePromptMixin,
    AIServiceToolLoopMixin,
    AIServiceRuntimeMixin,
):
    """Unified AI workflows for generation, branching and review."""

    def __init__(
        self,
        repository: SQLiteRepository,
        graph_service: GraphService,
        context_service: ContextService,
        validation_service: ValidationService,
        *,
        llm_provider: str | None = None,
        llm_platform_config: dict[str, Any] | None = None,
        llm_presets: dict[str, LLMPreset] | None = None,
        prompt_template_dir: str | None = None,
        state_service: StateService | None = None,
        setting_proposal_service: SettingProposalService | None = None,
    ) -> None:
        self.repository = repository
        self.graph_service = graph_service
        self.context_service = context_service
        self.validation_service = validation_service
        self.state_service = state_service
        self.setting_proposal_service = setting_proposal_service
        self.prompt_templates = PromptTemplateService(prompt_template_dir)
        self.context_assembler = ContextAssembler()
        self.readable_tool_service = ReadableContentToolService(
            repository,
            graph_service,
            state_service=state_service,
        )
        self.tool_service = ToolService(
            repository=repository,
            graph_service=graph_service,
            readable_tool_service=self.readable_tool_service,
            setting_proposal_service=setting_proposal_service,
        )
        self._default_platform_config = (llm_platform_config or {}).copy()
        self._llm_presets = dict(llm_presets or {})
        self._adapter_cache: dict[str, Any] = {}
        self._prompt_cache_monitor: dict[str, dict[str, Any]] = {}
        self._tool_loop_max_rounds = 6
        self._tool_loop_max_calls_per_round = 10
        self._tool_loop_single_read_char_limit = 4000
        self._tool_loop_total_read_char_limit = 20000
        self._tool_loop_no_progress_limit = 2
        self._tool_write_proposal_enabled = False
        self.llm_adapter = create_llm_adapter(
            llm_provider,
            platform_config=self._default_platform_config,
        )
        self._single_workflow = self._build_single_workflow()
        self._chapter_multi_workflow = self._build_chapter_multi_workflow()

    def set_setting_proposal_service(self, service: Any | None) -> None:
        self.setting_proposal_service = service
        self.tool_service.set_setting_proposal_service(service)

    def _execute_tool_call(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        project_id: str,
        tool_context_node_id: str = "",
        tool_thread_id: str = "",
        write_proposal_enabled: bool = False,
        write_document_enabled: bool = False,
        allow_skip_document: bool = False,
        node_tools_enabled: bool = False,
        tool_response_cache: dict[str, tuple[Any, int, dict[str, Any]]] | None = None,
        single_read_char_limit: int = 4000,
        total_read_char_limit: int = 20000,
        total_read_chars: int = 0,
    ) -> tuple[Any, int, dict[str, Any]]:
        cache = tool_response_cache if isinstance(tool_response_cache, dict) else {}
        return self.tool_service.execute_tool_call(
            tool_name=tool_name,
            arguments=arguments,
            project_id=project_id,
            tool_context_node_id=tool_context_node_id,
            tool_thread_id=tool_thread_id,
            write_proposal_enabled=write_proposal_enabled,
            write_document_enabled=write_document_enabled,
            allow_skip_document=allow_skip_document,
            node_tools_enabled=node_tools_enabled,
            tool_response_cache=cache,
            single_read_char_limit=single_read_char_limit,
            total_read_char_limit=total_read_char_limit,
            total_read_chars=total_read_chars,
        )
