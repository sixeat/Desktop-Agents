import asyncio
import json
from typing import AsyncIterator

import aiohttp

from core.llm_settings import load_llm_settings


class OpenAICompatibleClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        timeout: int = 60,
    ):
        settings = load_llm_settings()
        self.api_key = api_key if api_key is not None else settings.api_key
        self.base_url = (base_url if base_url is not None else settings.base_url).rstrip("/")
        self.model = model if model is not None else settings.model
        self.provider = provider if provider is not None else settings.provider
        self.timeout = timeout

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _missing_api_key_message(self) -> str:
        return f"{self.provider} API Key 未配置，请在 API Key 设置中配置后再试。"

    async def complete(
        self,
        messages: list[dict],
        temperature: float = 0.7,
    ) -> dict:
        if not self.api_key:
            return {"role": "assistant", "content": self._missing_api_key_message()}

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
                async with session.post(self.endpoint, json=payload) as resp:
                    if resp.status != 200:
                        return {"role": "assistant", "content": await self._http_error_message(resp)}
                    data = await resp.json()
                    message = data["choices"][0]["message"]
                    if "role" not in message:
                        message["role"] = "assistant"
                    return message
        except asyncio.TimeoutError:
            return {"role": "assistant", "content": f"{self.provider} 请求超时，请稍后再试。"}
        except aiohttp.ClientError:
            return {"role": "assistant", "content": f"{self.provider} 网络请求失败，请检查网络后再试。"}
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            return {"role": "assistant", "content": f"{self.provider} 返回格式异常，请稍后再试。"}

    async def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        message = await self.complete(messages, temperature=temperature)
        return str(message.get("content") or "")

    async def chat_stream(self, messages: list[dict], temperature: float = 0.7) -> AsyncIterator[str]:
        if not self.api_key:
            yield self._missing_api_key_message()
            return

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(headers=self.headers, timeout=timeout) as session:
                async with session.post(self.endpoint, json=payload) as resp:
                    if resp.status != 200:
                        yield await self._http_error_message(resp)
                        return
                    async for raw_line in resp.content:
                        line = raw_line.decode("utf-8", errors="ignore").strip()
                        if not line.startswith("data:"):
                            continue
                        chunk = line.removeprefix("data:").strip()
                        if chunk == "[DONE]":
                            break
                        try:
                            obj = json.loads(chunk)
                            delta = obj["choices"][0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                            continue
        except asyncio.TimeoutError:
            yield f"{self.provider} 请求超时，请稍后再试。"
        except aiohttp.ClientError:
            yield f"{self.provider} 网络请求失败，请检查网络后再试。"

    async def _http_error_message(self, resp: aiohttp.ClientResponse) -> str:
        if resp.status == 401:
            return f"{self.provider} 认证失败，请检查 LLM_API_KEY。"
        if resp.status == 429:
            return "LLM 请求过于频繁，请稍后再试。"
        if 500 <= resp.status:
            return "LLM 服务暂时不可用，请稍后再试。"

        detail = await resp.text()
        if detail:
            return f"LLM 请求失败（HTTP {resp.status}）。"
        return f"LLM 请求失败（HTTP {resp.status}）。"

    async def close(self):
        return None


DeepSeekClient = OpenAICompatibleClient
