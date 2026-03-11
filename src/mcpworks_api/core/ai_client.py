"""Lightweight httpx-based AI provider client.

Used server-side to relay messages to an agent's configured AI engine.
No heavy SDK dependencies — just httpx calls to provider REST APIs.
"""

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

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
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
