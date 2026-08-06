"""Model abstraction layer.

Lets you switch between OpenAI, Anthropic, Gemini, Ollama and any
OpenAI-compatible third-party API purely via environment configuration.
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class ProviderSpec:
    """Static configuration for a supported model provider."""

    family: str
    base_url: Optional[str] = None
    key_env: Optional[str] = None


# Canonical provider key -> provider spec (family, optional default base URL,
# and optional dedicated key env var). OpenAI-compatible providers share the
# "openai" family; each entry consolidates the three parallel dicts that used to
# map family / base_url / key_env separately.
PROVIDERS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec("openai"),
    "azure": ProviderSpec("openai"),
    "openrouter": ProviderSpec("openai", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "deepseek": ProviderSpec("openai", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "groq": ProviderSpec("openai", "https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "together": ProviderSpec("openai", "https://api.together.xyz/v1", "TOGETHER_API_KEY"),
    "mistral": ProviderSpec("openai", "https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "opencode": ProviderSpec("openai", "https://opencode.ai/zen/v1", "OPENCODE_API_KEY"),
    "local": ProviderSpec("openai"),
    "custom": ProviderSpec("openai"),
    "anthropic": ProviderSpec("anthropic"),
    "gemini": ProviderSpec("gemini"),
    "google": ProviderSpec("gemini"),
    "ollama": ProviderSpec("ollama"),
}

PROVIDER_ALIASES = PROVIDERS  # public, for --list-providers


def get_provider_spec(provider: str) -> ProviderSpec:
    """Return the spec for a provider key (defaulting to a plain openai spec)."""
    return PROVIDERS.get((provider or "").lower(), ProviderSpec("openai"))


@dataclass
class ModelConfig:
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    base_url: Optional[str] = None      # for OpenAI-compatible providers
    api_key: Optional[str] = None
    temperature: float = 0.3
    max_tokens: Optional[int] = 4096
    extra: dict = field(default_factory=dict)


def resolve_alias(provider: str) -> str:
    return get_provider_spec(provider).family


def _provider_key(cfg: ModelConfig, fallback_env: str) -> Optional[str]:
    """Resolve the API key: dedicated provider env > explicit cfg key > generic env.

    Providers with a dedicated key env var (e.g. OPENROUTER_API_KEY,
    OPENCODE_API_KEY) never fall back to the generic OPENAI_API_KEY, otherwise a
    stale/generic key would be sent to the wrong endpoint (causing 401s). A
    provider whose dedicated var is empty/absent is treated as keyless (many
    free tiers, e.g. OpenCode Zen free models, need no auth header at all).
    """
    provider = (cfg.provider or "").lower()
    if provider == "custom":
        return os.getenv("CUSTOM_API_KEY") or (cfg.api_key or os.getenv(fallback_env)) or None

    key_env = get_provider_spec(provider).key_env
    if key_env:
        value = os.getenv(key_env)
        return value if value else None
    if cfg.api_key:
        return cfg.api_key
    return os.getenv(fallback_env) or None


def _resolve_base_url(cfg: ModelConfig) -> Optional[str]:
    """Resolve the base URL for an OpenAI-compatible provider.

    A provider-specific default wins over the generic OPENAI_BASE_URL so that a
    provider like "openrouter" is never accidentally pointed at OpenAI's endpoint.
    """
    provider = (cfg.provider or "").lower()
    if provider == "openai":
        return cfg.base_url or os.getenv("OPENAI_BASE_URL")
    if provider == "custom":
        return (
            os.getenv("CUSTOM_BASE_URL")
            or cfg.base_url
            or os.getenv("OPENAI_BASE_URL")
        )
    default = get_provider_spec(provider).base_url
    if default:
        return default
    return cfg.base_url or os.getenv("OPENAI_BASE_URL")


def _keyless_client():
    """Build an httpx client that strips the Authorization header.

    Some OpenAI-compatible free tiers (e.g. OpenCode Zen free models) serve
    requests with NO auth header at all, while the langchain OpenAI SDK always
    attaches ``Authorization: Bearer <key>``. Passing an httpx.Client whose auth
    middleware removes that header lets us talk to such keyless endpoints.
    """
    import httpx

    class _NoAuth(httpx.Auth):
        def auth_flow(self, request):
            request.headers.pop("Authorization", None)
            yield request

    return httpx.Client(auth=_NoAuth())


def get_model(cfg: Optional[ModelConfig] = None):
    """Build a langchain chat model for the given config (env-based by default)."""
    cfg = cfg or model_config_from_env()
    family = resolve_alias(cfg.provider)
    kwargs = {"temperature": cfg.temperature}
    if cfg.max_tokens:
        kwargs["max_tokens"] = cfg.max_tokens

    if family == "openai":
        from langchain_openai import ChatOpenAI

        api_key = _provider_key(cfg, "OPENAI_API_KEY")
        kwargs.setdefault("http_client", _keyless_client() if not api_key else None)
        return ChatOpenAI(
            model=cfg.model,
            api_key=api_key,
            base_url=_resolve_base_url(cfg),
            **kwargs,
        )

    if family == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=cfg.model,
            api_key=_provider_key(cfg, "ANTHROPIC_API_KEY"),
            **kwargs,
        )

    if family == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=cfg.model,
            api_key=_provider_key(cfg, "GEMINI_API_KEY"),
            **kwargs,
        )

    if family == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=cfg.model,
            base_url=cfg.base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            **kwargs,
        )

    raise ValueError(f"Unsupported provider: {cfg.provider}")


def model_config_from_env() -> ModelConfig:
    raw_max_tokens = os.getenv("MODEL_MAX_TOKENS", "").strip()
    return ModelConfig(
        provider=os.getenv("MODEL_PROVIDER", "openai"),
        model=os.getenv("MODEL_NAME", os.getenv("OPENAI_MODEL", "gpt-4o-mini")),
        base_url=os.getenv("OPENAI_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY"),
        temperature=float(os.getenv("MODEL_TEMPERATURE", "0.3")),
        max_tokens=int(raw_max_tokens) if raw_max_tokens else 4096,
    )