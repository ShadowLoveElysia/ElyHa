"""
异步 LLM 请求分发器 - 统一的异步请求入口

支持平台：
- OpenAI 及兼容 API
- Anthropic Claude
- Google Gemini
- Amazon Bedrock
- Cohere
- 本地模型 (LocalLLM, Sakura)
"""

import asyncio
import json
from typing import Tuple, Optional

import aiohttp

from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.LLMRequester.AsyncOpenaiRequester import AsyncOpenaiRequester
from ModuleFolders.Infrastructure.LLMRequester.ErrorClassifier import ErrorClassifier, ErrorType
from ModuleFolders.Infrastructure.LLMRequester.AsyncSignalHub import get_signal_hub
from ModuleFolders.Infrastructure.LLMRequester.LLMClientFactory import LLMClientFactory


class AsyncLLMRequester(Base):
    """异步 LLM 请求分发器"""

    # 全局连接池
    _session: Optional[aiohttp.ClientSession] = None
    _session_lock = asyncio.Lock()
    _current_limit: int = 0  # 记录当前连接池限制

    def __init__(self) -> None:
        super().__init__()

    @classmethod
    async def get_session(cls, max_connections: int = 100) -> aiohttp.ClientSession:
        """
        获取全局 aiohttp 会话

        Args:
            max_connections: 最大连接数，应与用户设置的线程数一致

        Note:
            连接池限制是为了保护本地系统资源（文件描述符、端口数），
            而非API限速。即使API没有429限制，本地系统也有上限。
            这确保高并发是"稳态暴力"而非"自杀式冲击"。
        """
        # 如果连接池限制变化，需要重建会话
        need_rebuild = (
            cls._session is None or
            cls._session.closed or
            cls._current_limit != max_connections
        )

        if need_rebuild:
            async with cls._session_lock:
                if cls._session and not cls._session.closed and cls._current_limit == max_connections:
                    return cls._session

                # 关闭旧会话
                if cls._session and not cls._session.closed:
                    await cls._session.close()

                # 创建新会话，连接数与用户设置的线程数关联
                connector = aiohttp.TCPConnector(
                    limit=max_connections * 2,  # 总连接数 = 线程数 * 2（留有余量）
                    limit_per_host=max_connections,  # 每主机连接数 = 线程数
                    ttl_dns_cache=300,
                    enable_cleanup_closed=True,
                )
                timeout = aiohttp.ClientTimeout(total=300, connect=30, sock_read=120)
                cls._session = aiohttp.ClientSession(connector=connector, timeout=timeout)
                cls._current_limit = max_connections

        return cls._session

    @classmethod
    async def close_session(cls) -> None:
        """关闭全局会话"""
        if cls._session and not cls._session.closed:
            await cls._session.close()
            cls._session = None

    def _normalize_transport(self, platform_config: dict) -> str:
        raw = str(platform_config.get("llm_transport", "") or "").strip().lower()
        if raw in {"openai_sdk", "openai-client", "openai_client"}:
            return "openai"
        if raw in {"anthropic_sdk", "anthropic-client", "anthropic_client"}:
            return "anthropic"
        if raw in {"httpx", "openai", "anthropic"}:
            return raw
        return "httpx"

    @staticmethod
    def _parse_tool_arguments(raw_args) -> dict:
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            try:
                parsed = json.loads(raw_args)
            except Exception:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _extract_anthropic_content(self, content_blocks: list[dict]) -> tuple[str, str, list[dict]]:
        response_content = ""
        response_think = ""
        tool_calls: list[dict] = []
        for block in content_blocks:
            block_type = str(block.get("type", "") or "").strip().lower()
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
        return response_think, response_content, tool_calls

    @staticmethod
    def _build_tool_call_response(tool_calls: list[dict], content_text: str = "") -> str:
        payload: dict = {"action": "tool_calls", "tool_calls": tool_calls}
        clean = str(content_text or "").strip()
        if clean:
            payload["final_answer"] = clean
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _normalize_openai_tool_choice(raw_choice):
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

    @staticmethod
    def _normalize_anthropic_tool_choice(raw_choice):
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

    async def send_request_async(
        self,
        messages: list,
        system_prompt: str,
        platform_config: dict
    ) -> Tuple[bool, str, str, int, int]:
        """
        异步分发请求到对应平台

        Returns:
            tuple: (skip, think, content, prompt_tokens, completion_tokens)
        """
        config = self.load_config()
        max_retries = 3 if config.get("enable_retry_backoff", True) else 1
        current_retry = 0
        backoff_delay = 2
        signal_hub = get_signal_hub()

        while current_retry < max_retries:
            # 检查停止信号
            if Base.work_status == Base.STATUS.STOPING or await signal_hub.check_stop():
                return True, "STOPPED", "Task stopped by user", 0, 0

            # 检查暂停信号
            await signal_hub.wait_if_paused()

            target_platform = platform_config.get("target_platform")
            api_format = platform_config.get("api_format")
            llm_transport = str(platform_config.get("llm_transport", "") or "").strip().lower()
            target_text = str(target_platform or "")
            transport_override_allowed = (
                target_text.startswith("custom_platform_")
                or target_text in {"anthropic", "openai", ""}
            )

            try:
                # 根据平台分发请求
                if llm_transport == "anthropic" and transport_override_allowed:
                    result = await self._request_anthropic_async(messages, system_prompt, platform_config)
                elif target_platform == "sakura":
                    result = await self._request_sakura_async(messages, system_prompt, platform_config)
                elif target_platform == "murasaki":
                    result = await self._request_sakura_async(messages, system_prompt, platform_config)
                elif target_platform == "LocalLLM":
                    result = await self._request_local_async(messages, system_prompt, platform_config)
                elif target_platform == "google" or (target_platform.startswith("custom_platform_") and api_format == "Google"):
                    result = await self._request_google_async(messages, system_prompt, platform_config)
                elif target_platform == "anthropic" or (target_platform.startswith("custom_platform_") and api_format == "Anthropic"):
                    result = await self._request_anthropic_async(messages, system_prompt, platform_config)
                else:
                    # OpenAI 及兼容 API
                    requester = AsyncOpenaiRequester()
                    result = await requester.request_openai_async(messages, system_prompt, platform_config)

                skip, think, content, pt, ct = result
                if not skip:
                    return result

                # 检查错误类型决定是否重试
                error_type, _ = ErrorClassifier.classify(content)
                if error_type == ErrorType.HARD_ERROR:
                    # 硬伤错误不重试
                    return result

            except Exception as e:
                error_str = str(e)
                error_type, _ = ErrorClassifier.classify(error_str)

                if error_type == ErrorType.HARD_ERROR:
                    # 硬伤错误不重试
                    return True, "HARD_ERROR", error_str, 0, 0

                result = (True, "SOFT_ERROR", error_str, 0, 0)

            current_retry += 1
            if current_retry < max_retries:
                if Base.work_status == Base.STATUS.STOPING:
                    return True, "STOPPED", "Task stopped by user", 0, 0
                self.print(f"[[yellow]RETRY[/]] Async request failed. Retrying in {backoff_delay}s... ({current_retry}/{max_retries-1})")
                await asyncio.sleep(backoff_delay)
                backoff_delay *= 2

        return result

    async def _request_anthropic_async(
        self,
        messages: list,
        system_prompt: str,
        platform_config: dict
    ) -> Tuple[bool, str, str, int, int]:
        """异步 Anthropic 请求"""
        try:
            model_name = platform_config.get("model_name")
            api_url = str(platform_config.get("api_url", "") or "").strip().rstrip("/")
            if not api_url:
                raise ValueError(
                    "api_url is required for this provider. "
                    "Please configure your provider endpoint in runtime profile."
                )
            api_key = platform_config.get("api_key")
            request_timeout = int(platform_config.get("request_timeout", 120) or 120)
            temperature = platform_config.get("temperature", 1.0)
            top_p = platform_config.get("top_p", 1.0)
            max_tokens = int(platform_config.get("max_tokens", 4096) or 4096)
            think_switch = bool(platform_config.get("think_switch", False))
            think_budget = int(
                platform_config.get("thinking_budget")
                or platform_config.get("think_budget")
                or 10000
            )
            extra_body = platform_config.get("extra_body", {})
            transport = self._normalize_transport(platform_config)

            if transport == "anthropic":
                sdk_config = dict(platform_config)
                sdk_config["api_url"] = api_url
                client = LLMClientFactory().get_anthropic_client(sdk_config)
                request_body = {
                    "model": model_name,
                    "max_tokens": max_tokens,
                    "messages": messages,
                    "timeout": request_timeout,
                }
                if system_prompt:
                    request_body["system"] = system_prompt
                if temperature != 1:
                    request_body["temperature"] = temperature
                if top_p != 1:
                    request_body["top_p"] = top_p
                if think_switch:
                    request_body["thinking"] = {"type": "enabled", "budget_tokens": max(128, think_budget)}
                native_tools = self._build_anthropic_tools(platform_config)
                if native_tools:
                    request_body["tools"] = native_tools
                    request_body["tool_choice"] = self._normalize_anthropic_tool_choice(
                        platform_config.get("native_tool_choice", {"type": "auto"})
                    )
                if isinstance(extra_body, dict) and extra_body:
                    request_body.update(extra_body)

                def _sync_call():
                    return client.messages.create(**request_body)

                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(None, _sync_call)
                blocks = list(response.content or [])
                normalized_blocks = []
                for block in blocks:
                    normalized_blocks.append(
                        {
                            "type": str(getattr(block, "type", "") or ""),
                            "text": str(getattr(block, "text", "") or ""),
                            "thinking": str(getattr(block, "thinking", "") or ""),
                            "name": str(getattr(block, "name", "") or ""),
                            "input": getattr(block, "input", {}),
                        }
                    )
                response_think, response_content, tool_calls = self._extract_anthropic_content(normalized_blocks)
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

            if transport == "openai":
                sdk_config = dict(platform_config)
                openai_base_url = api_url
                if openai_base_url.endswith("/chat/completions"):
                    openai_base_url = openai_base_url[:-17]
                if bool(platform_config.get("auto_complete", False)) and not openai_base_url.endswith("/v1"):
                    openai_base_url = f"{openai_base_url}/v1"
                sdk_config["api_url"] = openai_base_url
                client = LLMClientFactory().get_openai_client(sdk_config)

                request_messages = list(messages)
                if system_prompt:
                    request_messages = [{"role": "system", "content": system_prompt}] + request_messages
                request_body = {
                    "model": model_name,
                    "messages": request_messages,
                    "max_tokens": max_tokens,
                }
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

                def _sync_openai_call():
                    return client.chat.completions.create(timeout=request_timeout, **request_body)

                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(None, _sync_openai_call)
                message = response.choices[0].message
                response_content = message.content or ""
                response_think = getattr(message, "reasoning_content", "") or ""
                tool_calls = []
                raw_calls = getattr(message, "tool_calls", [])
                if isinstance(raw_calls, list):
                    for call in raw_calls:
                        fn = getattr(call, "function", None)
                        name = str(getattr(fn, "name", "") or "").strip()
                        if not name:
                            continue
                        args = self._parse_tool_arguments(getattr(fn, "arguments", {}))
                        tool_calls.append({"name": name, "arguments": args})
                if tool_calls:
                    response_content = self._build_tool_call_response(tool_calls, response_content)
                usage = getattr(response, "usage", None)
                prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or getattr(usage, "input_tokens", 0) or 0)
                completion_tokens = int(
                    getattr(usage, "completion_tokens", 0)
                    or getattr(usage, "output_tokens", 0)
                    or 0
                )
                return False, response_think, response_content, prompt_tokens, completion_tokens

            # 默认 HTTPX 模式
            request_body = {
                "model": model_name,
                "max_tokens": max_tokens,
                "messages": messages,
            }
            if system_prompt:
                request_body["system"] = system_prompt
            if temperature != 1:
                request_body["temperature"] = temperature
            if top_p != 1:
                request_body["top_p"] = top_p
            if think_switch:
                request_body["thinking"] = {"type": "enabled", "budget_tokens": max(128, think_budget)}
            native_tools = self._build_anthropic_tools(platform_config)
            if native_tools:
                request_body["tools"] = native_tools
                request_body["tool_choice"] = self._normalize_anthropic_tool_choice(
                    platform_config.get("native_tool_choice", {"type": "auto"})
                )
            if isinstance(extra_body, dict) and extra_body:
                request_body.update(extra_body)

            headers = {
                "x-api-key": api_key,
                "anthropic-version": str(platform_config.get("anthropic_version", "2023-06-01") or "2023-06-01"),
                "Content-Type": "application/json",
            }

            endpoint = api_url
            if not endpoint.endswith("/messages"):
                if endpoint.endswith("/v1"):
                    endpoint = f"{endpoint}/messages"
                else:
                    endpoint = f"{endpoint}/v1/messages"

            session = await self.get_session()
            timeout = aiohttp.ClientTimeout(total=request_timeout)

            async with session.post(endpoint, json=request_body, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"HTTP {resp.status}: {error_text}")
                response_json = await resp.json()

            content_blocks = response_json.get("content", [])
            parsed_blocks = content_blocks if isinstance(content_blocks, list) else []
            response_think, response_content, tool_calls = self._extract_anthropic_content(parsed_blocks)
            if tool_calls:
                response_content = self._build_tool_call_response(tool_calls, response_content)
            usage = response_json.get("usage", {})
            prompt_tokens = int(usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0) or 0)
            completion_tokens = int(usage.get("output_tokens", 0) or usage.get("completion_tokens", 0) or 0)
            return False, response_think, response_content, prompt_tokens, completion_tokens

        except Exception as e:
            error_str = str(e)
            error_type, _ = ErrorClassifier.classify(error_str)
            return True, error_type.value.upper(), error_str, 0, 0

    async def _request_google_async(
        self,
        messages: list,
        system_prompt: str,
        platform_config: dict
    ) -> Tuple[bool, str, str, int, int]:
        """异步 Google Gemini 请求"""
        try:
            model_name = platform_config.get("model_name")
            api_key = platform_config.get("api_key")
            request_timeout = platform_config.get("request_timeout", 120)
            temperature = platform_config.get("temperature", 1.0)

            # 构建 Gemini API URL
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

            # 转换消息格式
            contents = []
            for msg in messages:
                role = "user" if msg["role"] == "user" else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}]
                })

            request_body = {
                "contents": contents,
                "generationConfig": {
                    "temperature": temperature,
                }
            }

            if system_prompt:
                request_body["systemInstruction"] = {
                    "parts": [{"text": system_prompt}]
                }

            headers = {"Content-Type": "application/json"}

            session = await self.get_session()
            timeout = aiohttp.ClientTimeout(total=request_timeout)

            async with session.post(api_url, json=request_body, headers=headers, timeout=timeout) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"HTTP {resp.status}: {error_text}")

                response_json = await resp.json()

            # 解析响应
            candidates = response_json.get("candidates", [])
            if not candidates:
                raise Exception("No candidates in response")

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            response_content = "".join(p.get("text", "") for p in parts)

            usage = response_json.get("usageMetadata", {})
            prompt_tokens = usage.get("promptTokenCount", 0)
            completion_tokens = usage.get("candidatesTokenCount", 0)

            return False, "", response_content, prompt_tokens, completion_tokens

        except Exception as e:
            error_str = str(e)
            error_type, _ = ErrorClassifier.classify(error_str)
            return True, error_type.value.upper(), error_str, 0, 0

    async def _request_sakura_async(
        self,
        messages: list,
        system_prompt: str,
        platform_config: dict
    ) -> Tuple[bool, str, str, int, int]:
        """异步 Sakura 本地模型请求"""
        # Sakura 使用 OpenAI 兼容格式
        requester = AsyncOpenaiRequester()
        return await requester.request_openai_async(messages, system_prompt, platform_config)

    async def _request_local_async(
        self,
        messages: list,
        system_prompt: str,
        platform_config: dict
    ) -> Tuple[bool, str, str, int, int]:
        """异步本地 LLM 请求"""
        # LocalLLM 使用 OpenAI 兼容格式
        requester = AsyncOpenaiRequester()
        return await requester.request_openai_async(messages, system_prompt, platform_config)
