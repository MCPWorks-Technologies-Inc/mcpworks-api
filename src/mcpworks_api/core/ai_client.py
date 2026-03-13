"""Lightweight httpx-based AI provider client.

Used server-side to relay messages to an agent's configured AI engine.
No heavy SDK dependencies — just httpx calls to provider REST APIs.

Two interfaces:
- chat(): Simple message-in/text-out (used by chat_with_agent)
- chat_with_tools(): Tool-calling loop support (used by orchestrator)
"""

import json as json_mod

import httpx
import structlog

logger = structlog.get_logger()

OPENAI_COMPATIBLE_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "grok": "https://api.x.ai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "kimi": "https://api.moonshot.cn/v1",
    "ollama": "http://localhost:11434/v1",
}

PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "google": "gemini-2.5-pro",
    "openrouter": "anthropic/claude-sonnet-4",
    "grok": "grok-3",
    "deepseek": "deepseek-chat",
    "kimi": "moonshot-v1-128k",
    "ollama": "llama3.1:70b",
}


class AIClientError(Exception):
    pass


async def chat(
    engine: str,
    model: str,
    api_key: str,
    message: str,
    system_prompt: str | None = None,
    max_tokens: int = 4096,
) -> str:
    model = model or PROVIDER_DEFAULT_MODELS.get(engine, "")
    if not model:
        raise AIClientError(f"No model specified and no default for engine '{engine}'")

    if engine == "anthropic":
        return await _chat_anthropic(api_key, model, message, system_prompt, max_tokens)
    elif engine == "google":
        return await _chat_google(api_key, model, message, system_prompt)
    elif engine in OPENAI_COMPATIBLE_BASE_URLS:
        base_url = OPENAI_COMPATIBLE_BASE_URLS[engine]
        return await _chat_openai_compatible(
            api_key, base_url, model, message, system_prompt, max_tokens
        )
    else:
        raise AIClientError(f"Unsupported engine: {engine}")


async def _chat_anthropic(
    api_key: str,
    model: str,
    message: str,
    system_prompt: str | None,
    max_tokens: int,
) -> str:
    payload: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": message}],
    }
    if system_prompt:
        payload["system"] = system_prompt

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
    if resp.status_code != 200:
        raise AIClientError(f"Anthropic API error {resp.status_code}: {resp.text}")
    data = resp.json()
    return data["content"][0]["text"]


async def _chat_openai_compatible(
    api_key: str,
    base_url: str,
    model: str,
    message: str,
    system_prompt: str | None,
    max_tokens: int,
) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": message})

    auth_header = f"Bearer {api_key}"
    logger.warning(
        "openai_compat_request_diag",
        base_url=base_url,
        model=model,
        api_key_type=type(api_key).__name__,
        api_key_len=len(api_key) if isinstance(api_key, str) else -1,
        api_key_prefix=api_key[:8] if isinstance(api_key, str) and len(api_key) > 8 else "SHORT",
        auth_header_len=len(auth_header),
    )

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": auth_header,
                "content-type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
            },
        )
    if resp.status_code != 200:
        raise AIClientError(f"API error {resp.status_code}: {resp.text}")
    data = resp.json()
    return data["choices"][0]["message"]["content"] or ""


async def _chat_google(
    api_key: str,
    model: str,
    message: str,
    system_prompt: str | None,
) -> str:
    payload: dict = {
        "contents": [{"parts": [{"text": message}]}],
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            url,
            params={"key": api_key},
            headers={"content-type": "application/json"},
            json=payload,
        )
    if resp.status_code != 200:
        raise AIClientError(f"Google API error {resp.status_code}: {resp.text}")
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


async def chat_with_tools(
    engine: str,
    model: str,
    api_key: str,
    messages: list[dict],
    tools: list[dict],
    system_prompt: str | None = None,
    max_tokens: int = 4096,
) -> dict:
    """Send messages with tool definitions, return normalized response.

    Returns:
        {
            "content": [{"type": "text", "text": "..."} | {"type": "tool_use", "id", "name", "input"}],
            "stop_reason": "tool_use" | "end_turn" | "max_tokens",
            "usage": {"input_tokens": int, "output_tokens": int}
        }
    """
    model = model or PROVIDER_DEFAULT_MODELS.get(engine, "")
    if not model:
        raise AIClientError(f"No model specified and no default for engine '{engine}'")

    if engine == "anthropic":
        return await _tools_anthropic(api_key, model, messages, tools, system_prompt, max_tokens)
    elif engine == "google":
        return await _tools_google(api_key, model, messages, tools, system_prompt)
    elif engine in OPENAI_COMPATIBLE_BASE_URLS:
        base_url = OPENAI_COMPATIBLE_BASE_URLS[engine]
        return await _tools_openai(
            api_key, base_url, model, messages, tools, system_prompt, max_tokens
        )
    else:
        raise AIClientError(f"Unsupported engine: {engine}")


def _convert_tools_to_anthropic(tools: list[dict]) -> list[dict]:
    return [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("input_schema", {"type": "object", "properties": {}}),
        }
        for t in tools
    ]


def _convert_messages_to_anthropic(messages: list[dict]) -> list[dict]:
    out = []
    for msg in messages:
        if msg.get("role") == "tool_result":
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg["tool_use_id"],
                            "content": str(msg.get("content", "")),
                        }
                    ],
                }
            )
        elif msg.get("role") == "assistant" and isinstance(msg.get("content"), list):
            out.append(msg)
        else:
            out.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    return out


async def _tools_anthropic(
    api_key: str,
    model: str,
    messages: list[dict],
    tools: list[dict],
    system_prompt: str | None,
    max_tokens: int,
) -> dict:
    payload: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": _convert_messages_to_anthropic(messages),
        "tools": _convert_tools_to_anthropic(tools),
    }
    if system_prompt:
        payload["system"] = system_prompt

    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
    if resp.status_code != 200:
        raise AIClientError(f"Anthropic API error {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    return {
        "content": data.get("content", []),
        "stop_reason": data.get("stop_reason", "end_turn"),
        "usage": {
            "input_tokens": data.get("usage", {}).get("input_tokens", 0),
            "output_tokens": data.get("usage", {}).get("output_tokens", 0),
        },
    }


def _convert_tools_to_openai(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


def _convert_messages_to_openai(messages: list[dict], system_prompt: str | None) -> list[dict]:
    out: list[dict] = []
    if system_prompt:
        out.append({"role": "system", "content": system_prompt})

    for msg in messages:
        role = msg.get("role", "user")
        if role == "tool_result":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": msg["tool_use_id"],
                    "content": str(msg.get("content", "")),
                }
            )
        elif role == "assistant" and isinstance(msg.get("content"), list):
            text_parts = []
            tool_calls = []
            for block in msg["content"]:
                if block.get("type") == "text":
                    text_parts.append(block["text"])
                elif block.get("type") == "tool_use":
                    tool_calls.append(
                        {
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": json_mod.dumps(block["input"]),
                            },
                        }
                    )
            entry: dict = {"role": "assistant", "content": "\n".join(text_parts) or None}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            out.append(entry)
        else:
            out.append({"role": role, "content": msg.get("content", "")})
    return out


async def _tools_openai(
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict],
    tools: list[dict],
    system_prompt: str | None,
    max_tokens: int,
) -> dict:
    payload: dict = {
        "model": model,
        "messages": _convert_messages_to_openai(messages, system_prompt),
        "tools": _convert_tools_to_openai(tools),
        "max_tokens": max_tokens,
    }

    auth_header = f"Bearer {api_key}"
    logger.warning(
        "openai_tools_request_diag",
        base_url=base_url,
        model=model,
        api_key_type=type(api_key).__name__,
        api_key_len=len(api_key) if isinstance(api_key, str) else -1,
        api_key_prefix=api_key[:8] if isinstance(api_key, str) and len(api_key) > 8 else "SHORT",
        auth_header_len=len(auth_header),
    )

    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": auth_header,
                "content-type": "application/json",
            },
            json=payload,
        )
    if resp.status_code != 200:
        raise AIClientError(f"API error {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    choice = data["choices"][0]
    message = choice["message"]

    content: list[dict] = []
    if message.get("content"):
        content.append({"type": "text", "text": message["content"]})
    for tc in message.get("tool_calls") or []:
        try:
            args = json_mod.loads(tc["function"]["arguments"])
        except (json_mod.JSONDecodeError, KeyError):
            args = {}
        content.append(
            {
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["function"]["name"],
                "input": args,
            }
        )

    finish = choice.get("finish_reason", "stop")
    stop_reason = "tool_use" if finish == "tool_calls" else "end_turn"

    usage = data.get("usage", {})
    return {
        "content": content,
        "stop_reason": stop_reason,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


def _convert_tools_to_google(tools: list[dict]) -> list[dict]:
    declarations = []
    for t in tools:
        schema = t.get("input_schema", {"type": "object", "properties": {}})
        decl: dict = {"name": t["name"], "description": t.get("description", "")}
        if schema.get("properties"):
            decl["parameters"] = schema
        declarations.append(decl)
    return [{"function_declarations": declarations}]


def _convert_messages_to_google(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for msg in messages:
        role = msg.get("role", "user")
        if role == "tool_result":
            out.append(
                {
                    "role": "function",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": msg.get("tool_name", "unknown"),
                                "response": {"result": msg.get("content", "")},
                            }
                        }
                    ],
                }
            )
        elif role == "assistant" and isinstance(msg.get("content"), list):
            parts = []
            for block in msg["content"]:
                if block.get("type") == "text":
                    parts.append({"text": block["text"]})
                elif block.get("type") == "tool_use":
                    parts.append({"functionCall": {"name": block["name"], "args": block["input"]}})
            out.append({"role": "model", "parts": parts})
        elif role == "assistant":
            out.append({"role": "model", "parts": [{"text": msg.get("content", "")}]})
        else:
            out.append({"role": "user", "parts": [{"text": msg.get("content", "")}]})
    return out


async def _tools_google(
    api_key: str,
    model: str,
    messages: list[dict],
    tools: list[dict],
    system_prompt: str | None,
) -> dict:
    payload: dict = {
        "contents": _convert_messages_to_google(messages),
        "tools": _convert_tools_to_google(tools),
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            url,
            params={"key": api_key},
            headers={"content-type": "application/json"},
            json=payload,
        )
    if resp.status_code != 200:
        raise AIClientError(f"Google API error {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    candidate = data["candidates"][0]
    parts = candidate.get("content", {}).get("parts", [])

    content: list[dict] = []
    has_tool_use = False
    for i, part in enumerate(parts):
        if "text" in part:
            content.append({"type": "text", "text": part["text"]})
        elif "functionCall" in part:
            has_tool_use = True
            fc = part["functionCall"]
            content.append(
                {
                    "type": "tool_use",
                    "id": f"google_call_{i}",
                    "name": fc["name"],
                    "input": fc.get("args", {}),
                }
            )

    stop_reason = "tool_use" if has_tool_use else "end_turn"
    usage_meta = data.get("usageMetadata", {})
    return {
        "content": content,
        "stop_reason": stop_reason,
        "usage": {
            "input_tokens": usage_meta.get("promptTokenCount", 0),
            "output_tokens": usage_meta.get("candidatesTokenCount", 0),
        },
    }
