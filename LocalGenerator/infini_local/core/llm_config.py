from __future__ import annotations

from infini_local.core.env_utils import env_bool, env_first, env_int, env_str


# LLM transport and generation policy configuration. This module owns env-derived
# provider settings; pipelines consume them but do not re-export them.
USE_LLM = env_bool("INFINI_USE_LLM", False)
ALLOW_DETERMINISTIC_DEV_FALLBACK = env_bool("INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK", False)

LLM_PROVIDER = env_str("INFINI_LLM_PROVIDER", "").lower()
LMSTUDIO_URL = env_first(("INFINI_LMSTUDIO_URL", "OPENAI_BASE_URL"), "http://127.0.0.1:1234").rstrip("/")
LMSTUDIO_MODEL = env_first(("INFINI_LMSTUDIO_MODEL", "OPENAI_MODEL"), "auto")

OPENROUTER_BASE_URL = env_str("INFINI_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
OPENROUTER_API_KEY = env_first(("INFINI_OPENROUTER_API_KEY", "OPENROUTER_API_KEY"), "")
OPENROUTER_MODEL = env_first(("INFINI_OPENROUTER_MODEL", "OPENROUTER_MODEL"), "auto")
OPENROUTER_HTTP_REFERER = env_str("INFINI_OPENROUTER_HTTP_REFERER", "https://github.com/InfiniCrafterLocal")
OPENROUTER_APP_TITLE = env_str("INFINI_OPENROUTER_APP_TITLE", "InfiniCrafterLocal")

OPENAI_COMPAT_BASE_URL = env_first(("INFINI_OPENAI_COMPAT_BASE_URL", "OPENAI_BASE_URL"), "").rstrip("/")
OPENAI_COMPAT_API_KEY = env_first(("INFINI_OPENAI_COMPAT_API_KEY", "OPENAI_API_KEY"), "")
OPENAI_COMPAT_MODEL = env_first(("INFINI_OPENAI_COMPAT_MODEL", "OPENAI_MODEL"), "auto")

LLM_FALLBACK_PROVIDER = env_str("INFINI_LLM_FALLBACK_PROVIDER", "").lower()
LLM_FALLBACK_MODEL = env_str("INFINI_LLM_FALLBACK_MODEL", "")
LLM_FALLBACK_BASE_URL = env_str("INFINI_LLM_FALLBACK_BASE_URL", "").rstrip("/")
LLM_FALLBACK_API_KEY = env_str("INFINI_LLM_FALLBACK_API_KEY", "")
LLM_FALLBACK_NETWORK_FAILS = env_int("INFINI_LLM_FALLBACK_NETWORK_FAILS", 2, lo=1, hi=10)

LLM_RESPONSE_FORMAT_MODE = env_str("INFINI_LLM_RESPONSE_FORMAT", "auto").lower()
LLM_MAX_TOKENS = env_int("INFINI_LLM_MAX_TOKENS", 9000, lo=256, hi=64000)
LLM_REASONING_MODE = env_str("INFINI_LLM_REASONING_MODE", "off").lower()
LLM_REASONING_MAX_TOKENS = env_int("INFINI_LLM_REASONING_MAX_TOKENS", 1500, lo=0, hi=32000)
LLM_REASONING_EXCLUDE = env_bool("INFINI_LLM_REASONING_EXCLUDE", True)
LLM_LOCAL_REASONING_PROMPT = env_bool("INFINI_LLM_LOCAL_REASONING_PROMPT", True)
