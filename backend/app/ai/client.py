import json
from collections.abc import AsyncGenerator

import httpx

from app.config import settings


class ClaudeClient:
    api_url = "https://api.anthropic.com/v1/messages"

    async def stream_text(
        self,
        *,
        system_prompt: str,
        user_content: str,
        model: str | None = None,
        max_tokens: int = 300,
    ) -> AsyncGenerator[str, None]:
        if not settings.anthropic_api_key:
            fallback = "좋아요. 그 부분을 네 말로 다시 설명해줄래? 왜 그런지 이유도 같이 말해줘."
            for ch in fallback:
                yield ch
            return

        headers = {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model or settings.anthropic_model,
            "max_tokens": max_tokens,
            "stream": True,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_content}],
        }

        timeout = httpx.Timeout(30.0, read=120.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", self.api_url, headers=headers, json=payload) as res:
                if res.status_code >= 400:
                    text = await res.aread()
                    raise RuntimeError(f"Claude API error: {res.status_code} {text.decode(errors='ignore')}")

                async for line in res.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    raw = line.removeprefix("data: ").strip()
                    if raw == "[DONE]":
                        break
                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("type") == "content_block_delta":
                        delta = obj.get("delta", {})
                        if delta.get("type") == "text_delta":
                            token = delta.get("text", "")
                            if token:
                                yield token

    async def complete_text(
        self,
        *,
        system_prompt: str,
        user_content: str,
        model: str | None = None,
        max_tokens: int = 400,
    ) -> str:
        if not settings.anthropic_api_key:
            return '{"score":80,"grade_label":"A","weak_points":["핵심 예시 부족"],"next_focus":"핵심 규칙과 반례를 1개씩 설명해보기","predicted_retention":0.75}'

        headers = {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model or settings.anthropic_model,
            "max_tokens": max_tokens,
            "stream": False,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_content}],
        }
        timeout = httpx.Timeout(30.0, read=120.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.post(self.api_url, headers=headers, json=payload)
            if res.status_code >= 400:
                raise RuntimeError(f"Claude API error: {res.status_code} {res.text}")
            data = res.json()
            parts = data.get("content", [])
            text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
            return text.strip()

