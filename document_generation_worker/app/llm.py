from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

from app.settings import Settings


@lru_cache(maxsize=1)
def _get_google_client(project_id: str, location: str):
    from google import genai

    return genai.Client(vertexai=True, project=project_id, location=location)


@lru_cache(maxsize=1)
def _get_anthropic_client(project_id: str, region: str):
    from anthropic import AnthropicVertex

    return AnthropicVertex(project_id=project_id, region=region)


@lru_cache(maxsize=1)
def _get_anthropic_api_client(api_key: str):
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=api_key)


async def stream_document_generation(
    *,
    prompt: str,
    settings: Settings,
) -> AsyncIterator[str]:
    provider = settings.document_generation_provider_name
    if provider == "google_vertex":
        async for text in _stream_with_google(prompt=prompt, settings=settings):
            yield text
        return
    if provider == "anthropic_vertex":
        async for text in _stream_with_anthropic(prompt=prompt, settings=settings):
            yield text
        return
    if provider == "anthropic_api":
        async for text in _stream_with_anthropic_api(prompt=prompt, settings=settings):
            yield text
        return
    raise ValueError(f"Unsupported document generation provider: {provider}")


async def _stream_with_google(
    *,
    prompt: str,
    settings: Settings,
) -> AsyncIterator[str]:
    from google.genai import types

    if not settings.gcp_project_id:
        raise ValueError("GCP_PROJECT_ID is required")
    client = _get_google_client(settings.gcp_project_id, settings.vertex_ai_location)
    stream = await client.aio.models.generate_content_stream(
        model=settings.effective_document_generation_model,
        contents=[prompt],
        config=types.GenerateContentConfig(
            temperature=0.4,
            top_p=0.95,
            candidate_count=1,
            max_output_tokens=settings.max_output_tokens,
        ),
    )
    async for response in stream:
        text = (getattr(response, "text", "") or "")
        if text:
            yield text


async def _stream_with_anthropic(
    *,
    prompt: str,
    settings: Settings,
) -> AsyncIterator[str]:
    if not settings.gcp_project_id:
        raise ValueError("GCP_PROJECT_ID is required")

    client = _get_anthropic_client(settings.gcp_project_id, settings.vertex_ai_location)
    queue: asyncio.Queue[Any] = asyncio.Queue()
    sentinel = object()
    loop = asyncio.get_running_loop()

    def _run_stream() -> None:
        try:
            with client.messages.stream(
                model=settings.effective_document_generation_model,
                max_tokens=settings.max_output_tokens,
                temperature=0.4,
                top_p=0.95,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text in stream.text_stream:
                    if text:
                        loop.call_soon_threadsafe(queue.put_nowait, text)
        except Exception as exc:  # pragma: no cover - exercised via async bridge
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, sentinel)

    task = asyncio.create_task(asyncio.to_thread(_run_stream))
    while True:
        item = await queue.get()
        if item is sentinel:
            break
        if isinstance(item, Exception):
            await task
            raise item
        yield item
    await task


async def _stream_with_anthropic_api(
    *,
    prompt: str,
    settings: Settings,
) -> AsyncIterator[str]:
    api_key = (settings.anthropic_api_key or "").strip()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required")

    client = _get_anthropic_api_client(api_key)
    async with client.messages.stream(
        model=settings.effective_document_generation_model,
        max_tokens=settings.max_output_tokens,
        temperature=0.4,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        async for text in stream.text_stream:
            if text:
                yield text
