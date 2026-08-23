from __future__ import annotations

import os
from dataclasses import dataclass

import dotenv
from langchain_openai import ChatOpenAI

from persona_studio.config import InfluencerConfig, REPO_ROOT

dotenv.load_dotenv(REPO_ROOT / ".env")


@dataclass(frozen=True)
class ApiSettings:
    api_key: str
    base_url: str
    model: str
    synthesis_model: str
    max_workers: int


def resolve_settings(
    influencer: InfluencerConfig | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    max_workers: int | None = None,
) -> ApiSettings:
    defaults = influencer.defaults if influencer else None
    resolved_key = (
        api_key
        or os.getenv("OPENAI_API_KEY")
    )
    if not resolved_key:
        raise ValueError(
            "No API key provided. Set OPENAI_API_KEY in .env or pass --api-key."
        )
    return ApiSettings(
        api_key=resolved_key,
        base_url=base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        model=model or (defaults.model if defaults else None) or os.getenv("MODEL_NAME", "gpt-4o-mini"),
        synthesis_model=(
            (defaults.synthesis_model if defaults and defaults.synthesis_model else None)
            or os.getenv("SYNTHESIS_MODEL_NAME")
            or os.getenv("MODEL_NAME", "gpt-4o-mini")
        ),
        max_workers=max_workers or (defaults.max_workers if defaults else 3),
    )


def make_llm(settings: ApiSettings, temperature: float = 0.1, max_tokens: int = 4096) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.model,
        openai_api_key=settings.api_key,
        openai_api_base=settings.base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=int(os.getenv("REQUEST_TIMEOUT", "120")),
    )
