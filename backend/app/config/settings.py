"""
Settings — Pydantic-based configuration for IPL Oracle backend.

All config lives here. Secrets (API keys) are loaded from .env.
Non-secret config (paths, thresholds) has sensible defaults.
"""

from __future__ import annotations

from enum import Enum

from pydantic_settings import BaseSettings


class SimulationMode(str, Enum):
    """
    Controls how much LLM involvement each simulation gets.

    PERSONA      — Full LLM persona mode. Every ball decided by LLM-as-cricketer.
                   Team communication enabled. Best for 1-10 sims (showcase).
    HYBRID       — LLM at high-leverage moments only, with persona prompts.
                   Communication via templates. Best for 10-100 sims (production).
    PROBABILISTIC — Zero LLM calls. Pure weighted probability sampling.
                    Current/legacy behavior. Best for 100-500 sims (fast).
    """

    PERSONA = "persona"
    HYBRID = "hybrid"
    PROBABILISTIC = "probabilistic"


class Settings(BaseSettings):
    # ------------------------------------------------------------------
    # App
    # ------------------------------------------------------------------
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    frontend_url: str = "http://localhost:5173"

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------
    default_sim_count: int = 100
    max_parallel_sims: int = 10
    llm_pressure_threshold: float = 0.85

    # Simulation mode: "persona", "hybrid", or "probabilistic"
    default_simulation_mode: str = "hybrid"

    # Auto-downgrade thresholds: if sim_count exceeds these, mode downgrades
    persona_max_sims: int = 10       # >10 sims → downgrade persona to hybrid
    hybrid_max_sims: int = 100       # >100 sims → downgrade hybrid to probabilistic

    # Tiered LLM model selection (by pressure level)
    llm_model_routine: str = ""      # Low pressure (<0.5): cheap/fast model
    llm_model_medium: str = ""       # Medium pressure (0.5-0.85)
    llm_model_clutch: str = ""       # High pressure (>=0.85): best model

    # ------------------------------------------------------------------
    # Graph DB (config, not a secret — no env var needed)
    # ------------------------------------------------------------------
    kuzu_db_path: str = "./data/kuzu_db"

    # ------------------------------------------------------------------
    # LLM Provider
    # ------------------------------------------------------------------
    # Which provider to use: anthropic | openai | gemini | local
    # Auto-detected from available API keys if not set.
    llm_provider: str = ""
    # Override the model name. If empty, uses the default for the chosen provider.
    llm_model: str = ""

    # ------------------------------------------------------------------
    # External APIs
    # ------------------------------------------------------------------
    openweathermap_api_key: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    openai_api_key: str = ""
    openai_model: str = ""
    gemini_api_key: str = ""

    # Local / self-hosted (Ollama, LM Studio, vLLM, etc.)
    # e.g. http://localhost:11434/v1  for Ollama
    local_llm_base_url: str = "http://localhost:11434/v1"
    local_llm_api_key: str = "ollama"  # placeholder — most local servers accept any key
    local_llm_model: str = "llama3.2"

    # ------------------------------------------------------------------
    # Optional integrations
    # ------------------------------------------------------------------
    mem0_api_key: str = ""
    serpapi_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
