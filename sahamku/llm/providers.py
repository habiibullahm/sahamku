"""Adapter LLM: Anthropic (Claude) atau Groq, dipilih lewat LLM_PROVIDER di .env."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sahamku.config import settings

log = logging.getLogger(__name__)


@dataclass
class LLMResult:
    text: str
    error: str | None = None  # pesan ramah untuk user jika gagal


class NotConfigured(Exception):
    pass


async def generate(system: str, user: str) -> LLMResult:
    provider = settings.llm_provider.lower()
    if provider == "groq":
        return await _groq(system, user)
    if provider == "anthropic":
        return await _anthropic(system, user)
    return LLMResult("", f"LLM_PROVIDER tidak dikenal: {provider}")


# ---------- Groq ----------

async def _groq(system: str, user: str) -> LLMResult:
    import groq

    if not settings.groq_api_key:
        return LLMResult("", "Fitur /ask belum aktif: GROQ_API_KEY belum diisi di .env")
    client = groq.AsyncGroq(api_key=settings.groq_api_key)
    try:
        resp = await client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=settings.groq_max_tokens,
            temperature=0.3,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
    except groq.AuthenticationError:
        return LLMResult("", "❌ GROQ_API_KEY tidak valid.")
    except groq.RateLimitError:
        return LLMResult("", "⏳ Kuota Groq (free tier) sedang penuh, coba lagi sebentar.")
    except groq.APIStatusError as e:
        log.error("groq status %s: %s", e.status_code, e.message)
        return LLMResult("", f"❌ Gagal menghubungi AI (HTTP {e.status_code}).")
    except groq.APIConnectionError:
        return LLMResult("", "❌ Tidak bisa terhubung ke layanan AI. Coba lagi.")
    choice = resp.choices[0] if resp.choices else None
    text = (choice.message.content or "").strip() if choice else ""
    return LLMResult(text)


# ---------- Anthropic ----------

async def _anthropic(system: str, user: str) -> LLMResult:
    import anthropic

    if not settings.anthropic_api_key:
        return LLMResult("", "Fitur /ask belum aktif: ANTHROPIC_API_KEY belum diisi di .env")
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        async with client.beta.messages.stream(
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            thinking={"type": "adaptive"},
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            msg = await stream.get_final_message()
    except anthropic.AuthenticationError:
        return LLMResult("", "❌ ANTHROPIC_API_KEY tidak valid.")
    except anthropic.RateLimitError:
        return LLMResult("", "⏳ Kuota API sedang penuh, coba lagi sebentar.")
    except anthropic.APIStatusError as e:
        log.error("anthropic status %s: %s", e.status_code, e.message)
        return LLMResult("", f"❌ Gagal menghubungi AI (HTTP {e.status_code}).")
    except anthropic.APIConnectionError:
        return LLMResult("", "❌ Tidak bisa terhubung ke layanan AI. Coba lagi.")
    if msg.stop_reason == "refusal":
        return LLMResult("", "Maaf, pertanyaan ini tidak bisa saya jawab.")
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    return LLMResult(text)
