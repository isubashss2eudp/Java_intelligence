from __future__ import annotations

"""
Multi-provider LLM factory.

Control which provider and model is used entirely from .env (or environment
variables).  No code changes are needed when switching between providers.

Required .env keys per provider
────────────────────────────────
  Gemini (default)
    LLM_PROVIDER=gemini
    LLM_MODEL=gemini-2.5-flash          # or gemini-2.5-pro, gemini-1.5-pro …
    GOOGLE_API_KEY=<your-key>

  OpenAI
    LLM_PROVIDER=openai
    LLM_MODEL=gpt-4o                    # or gpt-4.1, o3, o4-mini …
    OPENAI_API_KEY=<your-key>

  Anthropic
    LLM_PROVIDER=anthropic
    LLM_MODEL=claude-sonnet-4-5         # or claude-opus-4, claude-haiku-3-5 …
    ANTHROPIC_API_KEY=<your-key>

Optional (applies to all providers)
    LLM_TEMPERATURE=0.1                 # default 0.1
    LLM_MAX_TOKENS=4096                 # default 4096
    LLM_CONDENSE_MAX_TOKENS=256        # token cap for the condense LLM
"""

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel

# ── Load .env from project root ───────────────────────────────────────────────
# override=True keeps .env values over any conflicting system-level env vars
# (e.g. a corporate proxy overriding HTTPS_PROXY)
_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env", override=True)

# Propagate proxy settings so every underlying HTTP client picks them up
for _var in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY"):
    _val = os.getenv(_var, "").strip()
    if _val:
        os.environ[_var] = _val
        os.environ[_var.lower()] = _val


# ── Helpers ───────────────────────────────────────────────────────────────────

def _provider() -> str:
    return os.getenv("LLM_PROVIDER", "gemini").lower().strip()


def _model(default: str) -> str:
    return os.getenv("LLM_MODEL", default).strip()


def _temperature(default: float = 0.1) -> float:
    try:
        return float(os.getenv("LLM_TEMPERATURE", str(default)))
    except ValueError:
        return default


def _max_tokens(default: int = 4096) -> int:
    try:
        return int(os.getenv("LLM_MAX_TOKENS", str(default)))
    except ValueError:
        return default


def _condense_max_tokens() -> int:
    try:
        return int(os.getenv("LLM_CONDENSE_MAX_TOKENS", "256"))
    except ValueError:
        return 256


def _build_llm(temperature: float, max_tokens: int, **extra: Any) -> BaseChatModel:
    """
    Instantiate the correct LangChain chat model based on LLM_PROVIDER.

    All three providers implement BaseChatModel so they are interchangeable
    everywhere in the codebase (agents, RAG chains, code review, chat).
    """
    provider = _provider()

    # ── Google Gemini ─────────────────────────────────────────────────────────
    if provider == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            raise ImportError(
                "langchain-google-genai is not installed.\n"
                "Run: pip install langchain-google-genai"
            )
        model = _model("gemini-2.5-flash")
        api_key = os.getenv("GOOGLE_API_KEY", "")
        if not api_key:
            raise EnvironmentError(
                "GOOGLE_API_KEY is not set. Add it to your .env file."
            )
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            transport="rest",
            max_output_tokens=max_tokens,
            max_retries=3,
            google_api_key=api_key,
            **extra,
        )

    # ── OpenAI (GPT-4o, GPT-4.1, o3, o4-mini, …) ─────────────────────────────
    elif provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise ImportError(
                "langchain-openai is not installed.\n"
                "Run: pip install langchain-openai"
            )
        model = _model("gpt-4o")
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY is not set. Add it to your .env file."
            )
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=3,
            openai_api_key=api_key,
            **extra,
        )

    # ── Anthropic Claude (claude-sonnet-4-5, claude-opus-4, …) ───────────────
    elif provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise ImportError(
                "langchain-anthropic is not installed.\n"
                "Run: pip install langchain-anthropic"
            )
        model = _model("claude-sonnet-4-5")
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file."
            )
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=3,
            anthropic_api_key=api_key,
            **extra,
        )

    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER: '{provider}'. "
            "Choose one of: gemini, openai, anthropic"
        )


# ── Public API ────────────────────────────────────────────────────────────────

def load_llm() -> BaseChatModel:
    """
    Main reasoning LLM — used by agents, RAG chain, code review, and chat.

    Provider and model are read from the environment:
      LLM_PROVIDER  →  gemini | openai | anthropic
      LLM_MODEL     →  any model name supported by that provider
    """
    return _build_llm(
        temperature=_temperature(0.1),
        max_tokens=_max_tokens(4096),
    )


def load_condense_llm() -> BaseChatModel:
    """
    Lightweight LLM for condensing follow-up questions into standalone queries.

    Uses the same provider as load_llm() but with a smaller token budget
    and zero temperature for deterministic condensing.
    """
    return _build_llm(
        temperature=0.0,
        max_tokens=_condense_max_tokens(),
    )


def get_active_provider() -> str:
    """Return a human-readable string identifying the active provider + model."""
    provider = _provider()
    defaults = {"gemini": "gemini-2.5-flash", "openai": "gpt-4o", "anthropic": "claude-sonnet-4-5"}
    model = _model(defaults.get(provider, "unknown"))
    return f"{provider}/{model}"
