import httpx
import json

from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.LLMRequester.LLMClientFactory import LLMClientFactory
from ModuleFolders.Infrastructure.LLMRequester.ModelConfigHelper import ModelConfigHelper
from ModuleFolders.Infrastructure.LLMRequester.ErrorClassifier import ErrorClassifier
from ModuleFolders.Infrastructure.LLMRequester.ProviderFingerprint import ProviderFingerprint


class AnthropicRequester(Base):
    def __init__(self) -> None:
        pass

    def _normalize_transport(self, platform_config: dict) -> str:
        raw = str(platform_config.get("llm_transport", "") or "").strip().lower()
        if raw in {"openai_sdk", "openai-client", "openai_client"}:
            return "openai"
        if raw in {"anthropic_sdk", "anthropic-client", "anthropic_client"}:
            return "anthropic"
        if raw in {"httpx", "openai", "anthropic"}:
            return raw
        return "anthropic"

    def _resolve_api_url(self, platform_config: dict) -> str:
        api_url = str(platform_config.get("api_url", "") or "").strip()
        if api_url:
            return api_url
        raise ValueError(
            "api_url is required for this provider. "
            "Please configure your provider endpoint in runtime profile."
        )

    def _is_cache_supported(self, platform_config: dict) -> bool:
        api_url = str(platform_config.get("api_url", "") or "")
        fingerprint = ProviderFingerprint()
        return fingerprint.should_use_cache(api_url)

    def _disable_cache_for_api(self, platform_config: dict, error_msg: str) -> None:
        api_url = str(platform_config.get("api_url", "") or "")
        fingerprint = ProviderFingerprint()
        fingerprint.mark_cache_unsupported(api_url, error_msg)

    def _build_system_with_cache(self, system_prompt: str) -> list[dict]:
        return [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def _parse_tool_arguments(self, raw_args) -> dict:
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            try:
                parsed = json.loads(raw_args)
            except Exception:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _normalize_openai_tool_choice(self, raw_choice):
        if raw_choice is None:
            return None
        if isinstance(raw_choice, str):
            text = raw_choice.strip().lower()
            if text in {"auto", "none", "required"}:
                return text
            return raw_choice
        if isinstance(raw_choice, dict):
            choice_type = str(raw_choice.get("type", "")).strip().lower()
            if choice_type in {"auto", "none", "required"}:
                return choice_type
            return raw_choice
        return raw_choice

    def _normalize_anthropic_tool_choice(self, raw_choice):
        if raw_choice is None:
            return {"type": "auto"}
        if isinstance(raw_choice, str):
            text = raw_choice.strip().lower()
            if text in {"auto", "any"}:
                return {"type": text}
            if text == "none":
                return {"type": "auto"}
            return {"type": "tool", "name": raw_choice}
        if isinstance(raw_choice, dict):
            choice_type = str(raw_choice.get("type", "")).strip().lower()
            if choice_type in {"auto", "any"}:
                return {"type": choice_type}
            if choice_type == "none":
                return {"type": "auto"}
            if choice_type == "tool":
                name = str(raw_choice.get("name", "")).strip()
                if name:
                    return {"type": "tool", "name": name}
            return raw_choice
        return {"type": "auto"}

    def _build_openai_function_tools(self, platform_config: dict) -> list[dict]:
        raw_tools = platform_config.get("native_tools")
        if not isinstance(raw_tools, list):
            return []
        tools: list[dict] = []
        for item in raw_tools:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            description = str(item.get("description", "") or "")
            input_schema = item.get("input_schema")
            if not isinstance(input_schema, dict):
                input_schema = item.get("parameters")
            if not isinstance(input_schema, dict):
                input_schema = {"type": "object", "properties": {}}
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": input_schema,
                    },
                }
            )
        return tools

    def _build_anthropic_tools(self, platform_config: dict) -> list[dict]:
        raw_tools = platform_config.get("native_tools")
        if not isinstance(raw_tools, list):
            return []
        tools: list[dict] = []
        for item in raw_tools:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            description = str(item.get("description", "") or "")
            input_schema = item.get("input_schema")
            if not isinstance(input_schema, dict):
                input_schema = item.get("parameters")
            if not isinstance(input_schema, dict):
                input_schema = {"type": "object", "properties": {}}
            tools.append(
                {
                    "name": name,
                    "description": description,
                    "input_schema": input_schema,
                }
            )
        return tools

    def _normalize_openai_message_tool_calls(self, raw_calls) -> list[dict]:
        if not isinstance(raw_calls, list):
            return []
        normalized: list[dict] = []
        for call in raw_calls:
            if isinstance(call, dict):
                fn = call.get("function", {})
                name = str((fn or {}).get("name", "") or call.get("name", "")).strip()
                args = self._parse_tool_arguments((fn or {}).get("arguments", call.get("arguments", {})))
            else:
                fn = getattr(call, "function", None)
                name = str(getattr(fn, "name", "") or getattr(call, "name", "")).strip()
                args = self._parse_tool_arguments(getattr(fn, "arguments", getattr(call, "arguments", {})))
            if not name:
                continue
            normalized.append({"name": name, "arguments": args})
        return normalized

    def _build_tool_call_response(self, tool_calls: list[dict], content_text: str = "") -> str:
        payload: dict = {"action": "tool_calls", "tool_calls": tool_calls}
        clean_content = str(content_text or "").strip()
        if clean_content:
            payload["final_answer"] = clean_content
        return json.dumps(payload, ensure_ascii=False)

    def _extract_anthropic_content(self, blocks: list) -> tuple[str, str, list[dict]]:
        response_think = ""
        response_content = ""
        tool_calls: list[dict] = []
        for block in blocks:
            if isinstance(block, dict):
                block_type = str(block.get("type", "")).strip().lower()
                if block_type == "text":
                    response_content += str(block.get("text", "") or "")
                elif block_type == "thinking":
                    response_think += str(block.get("thinking", "") or "")
                elif block_type == "tool_use":
                    name = str(block.get("name", "") or "").strip()
                    if name:
                        tool_calls.append(
                            {
                                "name": name,
                                "arguments": self._parse_tool_arguments(block.get("input", {})),
                            }
                        )
                continue
            block_type = str(getattr(block, "type", "") or "").strip().lower()
            if block_type == "text":
                response_content += str(getattr(block, "text", "") or "")
            elif block_type == "thinking":
                response_think += str(getattr(block, "thinking", "") or "")
            elif block_type == "tool_use":
                name = str(getattr(block, "name", "") or "").strip()
                if name:
                    tool_calls.append(
                        {
                            "name": name,
                            "arguments": self._parse_tool_arguments(getattr(block, "input", {})),
                        }
                    )
        return response_think, response_content, tool_calls

    def _build_native_base_params(
        self,
        *,
        messages: list,
        system_prompt: str,
        platform_config: dict,
        use_cache: bool,
    ) -> dict:
        model_name = platform_config.get("model_name")
        request_timeout = int(platform_config.get("request_timeout", 60) or 60)
        temperature = platform_config.get("temperature", 1.0)
        top_p = platform_config.get("top_p", 1.0)
        think_switch = platform_config.get("think_switch")
        max_tokens = int(
            platform_config.get("max_tokens")
            or ModelConfigHelper.get_claude_max_output_tokens(model_name)
            or 4096
        )
        thinking_budget = int(
            platform_config.get("thinking_budget")
            or platform_config.get("think_budget")
            or 4096
        )
        extra_body = platform_config.get("extra_body", {})

        system_content: str | list[dict] | None = None
        if system_prompt:
            system_content = (
                self._build_system_with_cache(system_prompt)
                if use_cache
                else system_prompt
            )

        base_params: dict = {
            "model": model_name,
            "messages": messages,
            "timeout": request_timeout,
            "max_tokens": max_tokens,
        }
        if system_content is not None:
            base_params["system"] = system_content
        if temperature != 1:
            base_params["temperature"] = temperature
        if top_p != 1:
            base_params["top_p"] = top_p
        if think_switch:
            base_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": max(128, thinking_budget),
            }
        native_tools = self._build_anthropic_tools(platform_config)
        if native_tools:
            base_params["tools"] = native_tools
            base_params["tool_choice"] = self._normalize_anthropic_tool_choice(
                platform_config.get("native_tool_choice", {"type": "auto"})
            )
        if isinstance(extra_body, dict) and extra_body:
            base_params.update(extra_body)
        return base_params

    def _build_httpx_messages_endpoint(self, api_url: str) -> str:
        normalized = str(api_url or "").rstrip("/")
        if normalized.endswith("/messages"):
            return normalized
        if normalized.endswith("/v1"):
            return f"{normalized}/messages"
        return f"{normalized}/v1/messages"

    def _request_anthropic_sdk(
        self,
        *,
        base_params: dict,
        platform_config: dict,
        use_cache: bool,
        system_prompt: str,
        api_url: str,
    ) -> tuple[bool, str, str, int, int]:
        sdk_config = dict(platform_config)
        sdk_config["api_url"] = api_url
        client = LLMClientFactory().get_anthropic_client(sdk_config)
        try:
            response = client.messages.create(**base_params)
        except Exception as e:
            error_str = str(e)
            if use_cache and ErrorClassifier.is_cache_related_error(error_str):
                self._disable_cache_for_api(platform_config, error_str)
                self.print("[yellow]Cache not supported by this API, disabled automatically. Retrying...[/yellow]")
                base_params["system"] = system_prompt
                response = client.messages.create(**base_params)
            else:
                raise

        response_think, response_content, tool_calls = self._extract_anthropic_content(list(response.content or []))
        if tool_calls:
            response_content = self._build_tool_call_response(tool_calls, response_content)
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(
            getattr(usage, "output_tokens", 0)
            or getattr(usage, "completion_tokens", 0)
            or 0
        )
        return False, response_think, response_content, prompt_tokens, completion_tokens

    def _request_anthropic_httpx(
        self,
        *,
        base_params: dict,
        platform_config: dict,
        api_url: str,
    ) -> tuple[bool, str, str, int, int]:
        endpoint = self._build_httpx_messages_endpoint(api_url)
        headers = {
            "x-api-key": str(platform_config.get("api_key", "") or ""),
            "anthropic-version": str(platform_config.get("anthropic_version", "2023-06-01") or "2023-06-01"),
            "Content-Type": "application/json",
        }
        timeout = int(platform_config.get("request_timeout", 60) or 60)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(endpoint, json=base_params, headers=headers)
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
            payload = response.json()

        content_blocks = payload.get("content", [])
        response_think, response_content, tool_calls = self._extract_anthropic_content(
            content_blocks if isinstance(content_blocks, list) else []
        )
        if tool_calls:
            response_content = self._build_tool_call_response(tool_calls, response_content)
        usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
        prompt_tokens = int(usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("output_tokens", 0) or usage.get("completion_tokens", 0) or 0)
        return False, response_think, response_content, prompt_tokens, completion_tokens

    def _build_openai_base_url(self, api_url: str, auto_complete: bool) -> str:
        base_url = str(api_url or "").rstrip("/")
        if base_url.endswith("/chat/completions"):
            base_url = base_url[:-17]
        if auto_complete and not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return base_url

    def _request_openai_sdk_compat(
        self,
        *,
        messages: list,
        system_prompt: str,
        platform_config: dict,
        api_url: str,
    ) -> tuple[bool, str, str, int, int]:
        request_timeout = int(platform_config.get("request_timeout", 60) or 60)
        model_name = platform_config.get("model_name")
        temperature = platform_config.get("temperature", 1.0)
        top_p = platform_config.get("top_p", 1.0)
        extra_body = platform_config.get("extra_body", {})
        max_tokens = platform_config.get("max_tokens")

        request_messages = list(messages)
        if system_prompt:
            request_messages = [{"role": "system", "content": system_prompt}] + request_messages

        request_body: dict = {
            "model": model_name,
            "messages": request_messages,
        }
        if max_tokens:
            request_body["max_tokens"] = int(max_tokens)
        if temperature != 1:
            request_body["temperature"] = temperature
        if top_p != 1:
            request_body["top_p"] = top_p
        native_tools = self._build_openai_function_tools(platform_config)
        if native_tools:
            request_body["tools"] = native_tools
            request_body["tool_choice"] = self._normalize_openai_tool_choice(
                platform_config.get("native_tool_choice", "auto")
            )
        if isinstance(extra_body, dict) and extra_body:
            request_body.update(extra_body)

        sdk_config = dict(platform_config)
        sdk_config["api_url"] = self._build_openai_base_url(
            api_url,
            bool(platform_config.get("auto_complete", False)),
        )
        client = LLMClientFactory().get_openai_client(sdk_config)
        response = client.chat.completions.create(timeout=request_timeout, **request_body)

        message = response.choices[0].message
        response_content = message.content or ""
        tool_calls = self._normalize_openai_message_tool_calls(getattr(message, "tool_calls", []))
        if tool_calls:
            response_content = self._build_tool_call_response(tool_calls, response_content)
        response_think = getattr(message, "reasoning_content", "") or ""
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or getattr(usage, "input_tokens", 0) or 0)
        completion_tokens = int(
            getattr(usage, "completion_tokens", 0)
            or getattr(usage, "output_tokens", 0)
            or 0
        )
        return False, response_think, response_content, prompt_tokens, completion_tokens

    def request_anthropic(self, messages, system_prompt, platform_config) -> tuple[bool, str, str, int, int]:
        try:
            api_url = self._resolve_api_url(platform_config)
            transport = self._normalize_transport(platform_config)
            enable_caching = bool(platform_config.get("enable_prompt_caching", False))
            use_cache = enable_caching and self._is_cache_supported(platform_config)

            if transport == "openai":
                return self._request_openai_sdk_compat(
                    messages=messages,
                    system_prompt=system_prompt,
                    platform_config=platform_config,
                    api_url=api_url,
                )

            base_params = self._build_native_base_params(
                messages=messages,
                system_prompt=system_prompt,
                platform_config=platform_config,
                use_cache=use_cache,
            )

            if transport == "httpx":
                return self._request_anthropic_httpx(
                    base_params=base_params,
                    platform_config=platform_config,
                    api_url=api_url,
                )

            return self._request_anthropic_sdk(
                base_params=base_params,
                platform_config=platform_config,
                use_cache=use_cache,
                system_prompt=system_prompt,
                api_url=api_url,
            )
        except Exception as e:
            error_str = str(e)
            error_type, _ = ErrorClassifier.classify(error_str)
            if Base.work_status != Base.STATUS.STOPING:
                api_url = str(platform_config.get("api_url", "Unknown URL") or "Unknown URL")
                model_name = str(platform_config.get("model_name", "Unknown Model") or "Unknown Model")
                self.error(
                    f"Request error ({error_type.value}) [URL: {api_url}, Model: {model_name}] ... {e}",
                    e if self.is_debug() else None,
                )
            else:
                self.print(f"[dim]Request aborted due to stop signal: {e}[/dim]")
            return True, error_type.value.upper(), error_str, 0, 0
