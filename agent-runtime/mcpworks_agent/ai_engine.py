"""AI engine abstraction for agent containers.

Provides a unified interface for interacting with AI models from different
providers (Anthropic, OpenAI, Google, OpenRouter) within an agent container.

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
    ) -> None:
        self.engine = engine or AGENT_AI_ENGINE
        self.model = model or AGENT_AI_MODEL
        self.api_key = api_key or AGENT_AI_API_KEY
        self.system_prompt = system_prompt or AGENT_AI_SYSTEM_PROMPT

        if not self.engine:
            raise AIEngineError("AI engine not configured (AGENT_AI_ENGINE not set)")
        if not self.api_key:
            raise AIEngineError("AI API key not configured (AGENT_AI_API_KEY not set)")

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        """Send a prompt and return the full completion."""
        if self.engine == "anthropic":
            return await self._complete_anthropic(prompt, **kwargs)
        elif self.engine == "openai":
            return await self._complete_openai(prompt, **kwargs)
        elif self.engine == "google":
            return await self._complete_google(prompt, **kwargs)
        elif self.engine == "openrouter":
            return await self._complete_openrouter(prompt, **kwargs)
        else:
            raise AIEngineError(f"Unknown engine: {self.engine}")

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncGenerator[str, None]:
        """Stream completion chunks."""
        if self.engine == "anthropic":
            async for chunk in self._stream_anthropic(prompt, **kwargs):
                yield chunk
        elif self.engine in ("openai", "openrouter"):
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
            model=self.model or "claude-opus-4-5",
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
            model=self.model or "claude-opus-4-5",
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

        client = openai.AsyncOpenAI(api_key=self.api_key)
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt})
        response = await client.chat.completions.create(
            model=self.model or "gpt-4o",
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

        base_url = None
        if self.engine == "openrouter":
            base_url = "https://openrouter.ai/api/v1"

        client = openai.AsyncOpenAI(api_key=self.api_key, base_url=base_url)
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt})

        stream = await client.chat.completions.create(
            model=self.model or "gpt-4o",
            messages=messages,
            max_tokens=kwargs.get("max_tokens", 4096),
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    async def _complete_openrouter(self, prompt: str, **kwargs: Any) -> str:
        full = ""
        async for chunk in self._stream_openai_compatible(prompt, **kwargs):
            full += chunk
        return full

    async def _complete_google(self, prompt: str, **_kwargs: Any) -> str:
        try:
            import google.generativeai as genai
        except ImportError:
            raise AIEngineError("google-generativeai package not installed")

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(
            self.model or "gemini-1.5-pro",
            system_instruction=self.system_prompt or None,
        )
        response = await model.generate_content_async(prompt)
        return response.text
