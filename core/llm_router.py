
"""
core/llm_router.py — Smart LLM router for all service modules.

Routes each request to the right model/adapter based on:
  - source module (mentor, quant, codegen, signals)
  - difficulty level / quant domain
  - model availability (Mistral API → local Mistral → Claude solo)

For the mentor pipeline specifically:
  1. Mistral base → fast factual draft
  2. Claude Sonnet 4.6 → refine, deepen, add follow-up questions

llm_router is a singleton — initialised at startup in main.py.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional
from enum import Enum

import anthropic

from core.config import settings
from core.system_prompts import SYSTEM_PROMPTS

logger = logging.getLogger(__name__)

# Result dataclass 

@dataclass
class LLMResult:
    content:       str
    model_used:    str
    adapter_used:  Optional[str]
    input_tokens:  Optional[int]
    output_tokens: Optional[int]
    tokens_used:   Optional[int]
    latency_ms:    int

# Mistral availability 

_mistral_api_client = None
_mistral_available: Optional[bool] = None

async def _init_mistral() -> bool:
    """Try to initialise the Mistral API client. Returns True if successful."""
    global _mistral_api_client, _mistral_available
    if _mistral_available is not None:
        return _mistral_available

    if not settings.MISTRAL_API_KEY:
        logger.info("MISTRAL_API_KEY not set — Claude will handle all requests solo")
        _mistral_available = False
        return False

    try:
        from mistralai import Mistral
        _mistral_api_client = Mistral(api_key=settings.MISTRAL_API_KEY)
        _mistral_available = True
        logger.info(f"✅ Mistral API ready ({settings.MISTRAL_BASE_MODEL_NAME})")
        return True
    except Exception as e:
        logger.warning(f"Mistral init failed: {e} — falling back to Claude solo")
        _mistral_available = False
        return False

async def _mistral_complete(prompt: str, system: str, max_tokens: int = 800) -> Optional[str]:
    """Call Mistral API. Returns None if unavailable or fails."""
    if not _mistral_available or _mistral_api_client is None:
        return None
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = await loop.run_in_executor(
            None,
            lambda: _mistral_api_client.chat.complete(
                model=settings.MISTRAL_BASE_MODEL_NAME,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,
            )
        )
        return resp.choices[0].message.content
    except Exception as e:
        logger.warning(f"Mistral completion failed: {e}")
        return None

# Claude client 

def _get_claude_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

# Mentor routing 

async def _route_mentor(ctx) -> LLMResult:
    """
    Mentor dual-model pipeline:
      Mistral → fast factual draft (3-5 paragraphs)
      Claude  → refine, add examples/formulas, append follow-up questions
    """
    from core.system_prompts import build_mentor_prompts
    t0 = time.perf_counter()

    # Format RAG context block
    rag_block = ""
    if ctx.rag_passages:
        rag_block = "RELEVANT KNOWLEDGE BASE PASSAGES:\n"
        for i, p in enumerate(ctx.rag_passages, 1):
            rag_block += f"[{i}] {p}\n\n"

    # Build compact history string for Mistral
    history_text = ""
    if ctx.history:
        lines = [
            f"{'Student' if m.role == 'user' else 'Tutor'}: {m.content[:300]}"
            for m in ctx.history[-4:]
        ]
        history_text = "\nPrior conversation:\n" + "\n".join(lines) + "\n"

    # Step A: Mistral draft
    mistral_draft = ""
    mistral_system, mistral_user = build_mentor_prompts(ctx, stage="draft")
    draft_prompt = f"{rag_block}{history_text}\nStudent question: {ctx.new_question}\n\nDraft answer (3-5 paragraphs, factually accurate):"
    mistral_draft = await _mistral_complete(draft_prompt, mistral_system, max_tokens=800) or ""

    pipeline_mode = "dual_model" if mistral_draft else "claude_solo"
    logger.info(f"Mentor pipeline: {pipeline_mode} | difficulty={ctx.difficulty.value}")

    # Step B: Claude refinement or solo 
    claude_system, claude_user = build_mentor_prompts(ctx, stage="refine", draft=mistral_draft)
    claude_messages = [
        {"role": m.role.value, "content": m.content}
        for m in ctx.history[-10:]
        if m.role.value in ("user", "assistant")
    ]
    claude_messages.append({"role": "user", "content": claude_user})

    client = _get_claude_client()
    t_claude = time.perf_counter()
    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=2000,
        system=claude_system,
        messages=claude_messages,
    )
    claude_latency = int((time.perf_counter() - t_claude) * 1000)
    total_latency  = int((time.perf_counter() - t0) * 1000)

    content      = response.content[0].text
    input_toks   = response.usage.input_tokens
    output_toks  = response.usage.output_tokens

    return LLMResult(
        content=content,
        model_used=f"mistral+{settings.CLAUDE_MODEL}" if mistral_draft else settings.CLAUDE_MODEL,
        adapter_used=None,
        input_tokens=input_toks,
        output_tokens=output_toks,
        tokens_used=input_toks + output_toks,
        latency_ms=total_latency,
    )

# Public router singleton 

class LLMRouter:
    """
    Singleton router. Initialise at startup via await llm_router.initialize().
    Use in services:
        result = await llm_router.route_mentor(ctx)
    """

    async def initialize(self) -> None:
        await _init_mistral()
        logger.info(f"LLM Router ready | mistral={'on' if _mistral_available else 'off'} | claude={settings.CLAUDE_MODEL}")

    async def route_mentor(self, ctx) -> LLMResult:
        return await _route_mentor(ctx)

    @property
    def mistral_available(self) -> bool:
        return bool(_mistral_available)


llm_router = LLMRouter()