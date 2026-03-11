"""AI engine abstraction for agent containers.

Provides a unified interface for interacting with AI models from different
providers within an agent container. Most providers expose an OpenAI-compatible
chat completions API and are routed through a single code path with per-provider
base URLs. Anthropic and Google use their native SDKs.

Configuration is fetched from the MCPWorks API at startup and the API key
is decrypted server-side before being injected into the container environment.
"""

import logging
import os
from collections.abc import AsyncGenerator
from typing import Any

logger = logging.getLogger(__name__)

AGENT_AI_ENGINE = os.environ.get("AGENT_AI_ENGINE", "")
AGENT_AI_MODEL = os.environ.get("AGENT_AI_MODEL", "")
AGENT_AI_API_KEY = os.environ.get("AGENT_AI_API_KEY", "")
AGENT_AI_SYSTEM_PROMPT = os.environ.get("AGENT_AI_SYSTEM_PROMPT", "")
AGENT_AI_BASE_URL = os.environ.get("AGENT_AI_BASE_URL", "")

OPENAI_COMPATIBLE_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "grok": "https://api.x.ai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "kimi": "https://api.moonshot.cn/v1",
    "ollama": "http://localhost:11434/v1",
}

OPENAI_COMPATIBLE_DEFAULTS: dict[str, str] = {
    "openai": "gpt-4o",
    "openrouter": "anthropic/claude-sonnet-4",
    "grok": "grok-3",
    "deepseek": "deepseek-chat",
    "kimi": "moonshot-v1-128k",
    "ollama": "llama3.1:70b",
}


class AIEngineError(Exception):
    pass


class AIEngine:
    """Unified interface for AI model providers.

    Usage:
        engine = AIEngine()
        response = await engine.complete("What is 2+2?")
        async for chunk in engine.stream("Tell me a story"):
            print(chunk, end="", flush=True)
    """

    def __init__(
        self,
        engine: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        system_prompt: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.engine = engine or AGENT_AI_ENGINE
        self.model = model or AGENT_AI_MODEL
        self.api_key = api_key or AGENT_AI_API_KEY
        self.system_prompt = system_prompt or AGENT_AI_SYSTEM_PROMPT
        self.base_url = base_url or AGENT_AI_BASE_URL or None

        if not self.engine:
            raise AIEngineError("AI engine not configured (AGENT_AI_ENGINE not set)")
        if not self.api_key and self.engine != "ollama":
            raise AIEngineError("AI API key not configured (AGENT_AI_API_KEY not set)")

    def _is_openai_compatible(self) -> bool:
        return self.engine in OPENAI_COMPATIBLE_BASE_URLS

    def _get_base_url(self) -> str:
        if self.base_url:
            return self.base_url
        return OPENAI_COMPATIBLE_BASE_URLS.get(self.engine, "")

    def _get_default_model(self) -> str:
        if self.engine == "anthropic":
            return "claude-sonnet-4-20250514"
        if self.engine == "google":
            return "gemini-2.5-pro"
        return OPENAI_COMPATIBLE_DEFAULTS.get(self.engine, "gpt-4o")

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        """Send a prompt and return the full completion."""
        if self.engine == "anthropic":
            return await self._complete_anthropic(prompt, **kwargs)
        elif self.engine == "google":
            return await self._complete_google(prompt, **kwargs)
        elif self._is_openai_compatible():
            return await self._complete_openai(prompt, **kwargs)
        else:
            raise AIEngineError(f"Unknown engine: {self.engine}")

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncGenerator[str, None]:
        """Stream completion chunks."""
        if self.engine == "anthropic":
            async for chunk in self._stream_anthropic(prompt, **kwargs):
                yield chunk
        elif self._is_openai_compatible():
            async for chunk in self._stream_openai_compatible(prompt, **kwargs):
                yield chunk
        else:
            full = await self.complete(prompt, **kwargs)
            yield full

    async def _complete_anthropic(self, prompt: str, **kwargs: Any) -> str:
        try:
            import anthropic
        except ImportError:
            raise AIEngineError("anthropic package not installed")

        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        messages = [{"role": "user", "content": prompt}]
        response = await client.messages.create(
            model=self.model or self._get_default_model(),
            max_tokens=kwargs.get("max_tokens", 4096),
            system=self.system_prompt or anthropic.NOT_GIVEN,
            messages=messages,
        )
        return response.content[0].text

    async def _stream_anthropic(self, prompt: str, **kwargs: Any) -> AsyncGenerator[str, None]:
        try:
            import anthropic
        except ImportError:
            raise AIEngineError("anthropic package not installed")

        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        messages = [{"role": "user", "content": prompt}]
        async with client.messages.stream(
            model=self.model or self._get_default_model(),
            max_tokens=kwargs.get("max_tokens", 4096),
            system=self.system_prompt or anthropic.NOT_GIVEN,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def _complete_openai(self, prompt: str, **kwargs: Any) -> str:
        try:
            import openai
        except ImportError:
            raise AIEngineError("openai package not installed")

        base_url = self._get_base_url()
        client = openai.AsyncOpenAI(
            api_key=self.api_key or "ollama",
            base_url=base_url or None,
        )
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt})
        response = await client.chat.completions.create(
            model=self.model or self._get_default_model(),
            messages=messages,
            max_tokens=kwargs.get("max_tokens", 4096),
        )
        return response.choices[0].message.content or ""

    async def _stream_openai_compatible(
        self, prompt: str, **kwargs: Any
    ) -> AsyncGenerator[str, None]:
        try:
            import openai
        except ImportError:
            raise AIEngineError("openai package not installed")

        base_url = self._get_base_url()
        client = openai.AsyncOpenAI(
            api_key=self.api_key or "ollama",
            base_url=base_url or None,
        )
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt})

        stream = await client.chat.completions.create(
            model=self.model or self._get_default_model(),
            messages=messages,
            max_tokens=kwargs.get("max_tokens", 4096),
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    async def _complete_google(self, prompt: str, **_kwargs: Any) -> str:
        try:
            import google.generativeai as genai
        except ImportError:
            raise AIEngineError("google-generativeai package not installed")

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(
            self.model or self._get_default_model(),
            system_instruction=self.system_prompt or None,
        )
        response = await model.generate_content_async(prompt)
        return response.text
