"""Tool feature availability model (direct/BYOK backends only).

Derived from the former Nous-subscription feature matrix with all
managed-gateway entitlement paths removed: every ``managed_by_nous``
flag is now permanently False because the Nous Portal integration no
longer exists in this tree. Direct (bring-your-own-key) availability
logic is preserved unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Set

from hermes_cli.config import get_env_value, load_config
from utils import is_truthy_value


def is_managed_tool_gateway_ready(*_args, **_kwargs) -> bool:
    """Managed Tool Gateway probe — permanently not ready (integration removed)."""
    return False
from tools.tool_backend_helpers import (
    fal_key_is_configured,
    has_direct_modal_credentials,
    managed_nous_tools_enabled,
    normalize_browser_cloud_provider,
    normalize_modal_mode,
    resolve_modal_backend_state,
    resolve_openai_audio_api_key,
)


_DEFAULT_PLATFORM_TOOLSETS = {
    "cli": "hermes-cli",
}


def _uses_gateway(section: object) -> bool:
    """Return True when a config section explicitly opts into the gateway."""
    if not isinstance(section, dict):
        return False
    return is_truthy_value(section.get("use_gateway"), default=False)


def _selected_provider(section: object, name_key: str = "provider") -> Optional[str]:
    """Return the stored provider string for a config section dict.

    Mirrors :func:`tools.tool_backend_helpers.read_selection`'s semantics on
    an in-memory section dict: ``"nous"`` for the managed selection (stored
    ``nous`` value or legacy ``use_gateway: true``), a vendor name for BYOK
    picks, or ``None`` when no selection is stored. Keeping this in lockstep
    with the runtime resolver is what stops ``hermes status`` from lying.
    """
    if not isinstance(section, dict):
        return None
    if is_truthy_value(section.get("use_gateway"), default=False):
        return "nous"
    value = section.get(name_key)
    if value is None:
        return None
    name = str(value).strip().lower()
    return name or None


@dataclass(frozen=True)
class ToolFeatureState:
    key: str
    label: str
    included_by_default: bool
    available: bool
    active: bool
    managed_by_nous: bool
    direct_override: bool
    toolset_enabled: bool
    current_provider: str = ""
    explicit_configured: bool = False


@dataclass(frozen=True)
class ToolSubscriptionFeatures:
    subscribed: bool
    nous_auth_present: bool
    provider_is_nous: bool
    features: Dict[str, ToolFeatureState]
    account_info: object = None

    @property
    def web(self) -> ToolFeatureState:
        return self.features["web"]

    @property
    def image_gen(self) -> ToolFeatureState:
        return self.features["image_gen"]

    @property
    def tts(self) -> ToolFeatureState:
        return self.features["tts"]

    @property
    def stt(self) -> ToolFeatureState:
        return self.features["stt"]

    @property
    def browser(self) -> ToolFeatureState:
        return self.features["browser"]

    @property
    def video_gen(self) -> ToolFeatureState:
        return self.features["video_gen"]

    @property
    def modal(self) -> ToolFeatureState:
        return self.features["modal"]

    def items(self) -> Iterable[ToolFeatureState]:
        ordered = ("web", "image_gen", "video_gen", "tts", "stt", "browser", "modal")
        for key in ordered:
            yield self.features[key]


def _model_config_dict(config: Dict[str, object]) -> Dict[str, object]:
    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        return dict(model_cfg)
    if isinstance(model_cfg, str) and model_cfg.strip():
        return {"default": model_cfg.strip()}
    return {}


def _toolset_enabled(config: Dict[str, object], toolset_key: str) -> bool:
    from toolsets import resolve_toolset

    platform_toolsets = config.get("platform_toolsets")
    if not isinstance(platform_toolsets, dict) or not platform_toolsets:
        platform_toolsets = {"cli": [_DEFAULT_PLATFORM_TOOLSETS["cli"]]}

    target_tools = set(resolve_toolset(toolset_key))
    if not target_tools:
        return False

    for platform, raw_toolsets in platform_toolsets.items():
        if isinstance(raw_toolsets, list):
            toolset_names = list(raw_toolsets)
        else:
            default_toolset = _DEFAULT_PLATFORM_TOOLSETS.get(platform)
            toolset_names = [default_toolset] if default_toolset else []
        if not toolset_names:
            default_toolset = _DEFAULT_PLATFORM_TOOLSETS.get(platform)
            if default_toolset:
                toolset_names = [default_toolset]

        available_tools: Set[str] = set()
        for toolset_name in toolset_names:
            if not isinstance(toolset_name, str) or not toolset_name:
                continue
            try:
                available_tools.update(resolve_toolset(toolset_name))
            except Exception:
                continue

        if target_tools and target_tools.issubset(available_tools):
            return True

    return False


def _has_agent_browser() -> bool:
    import shutil

    from hermes_constants import agent_browser_runnable

    # agent-browser is no longer a root package.json dependency (#43564) — it
    # resolves lazily via npx for most installs, which a bare PATH +
    # node_modules probe can't see. Mirror the local-CLI tail of
    # :func:`tools.browser_tool.check_browser_requirements` (same cascade, same
    # Termux carve-out) so the setup/status surfaces can't diverge from what
    # browser tools actually find at runtime; validate=False keeps this a cheap
    # existence check with no subprocess spawn.
    try:
        from tools.browser_tool import (
            _find_agent_browser,
            _requires_real_termux_browser_install,
        )
    except Exception:
        # If the runtime probe can't be imported, fall back to binary presence
        # (prior behaviour) rather than crashing the setup/status surface.
        # Validate the resolved binary actually runs — a dangling global
        # symlink (issue #48521) is reported by ``which`` but fails at exec.
        if agent_browser_runnable(shutil.which("agent-browser")):
            return True

        # Hermes-managed Node dirs (Windows installer / POSIX $HERMES_HOME/node)
        # are prepended to PATH at runtime but usually absent from the *probe*
        # process's PATH. Without this rung a successful install keeps
        # reporting "needs setup" on Windows.
        from hermes_constants import with_hermes_node_path
        managed_path = with_hermes_node_path().get("PATH", "")
        if managed_path:
            managed_hit = shutil.which("agent-browser", path=managed_path)
            if managed_hit and agent_browser_runnable(managed_hit):
                return True

        # Local node_modules/.bin: resolve via PATHEXT-aware ``shutil.which`` so
        # Windows picks the executable ``.cmd`` shim — probing the
        # extensionless POSIX shim directly fails exec (WinError 193) even
        # right after a successful ``npm install``.
        local_bin_dir = Path(__file__).parent.parent / "node_modules" / ".bin"
        if local_bin_dir.is_dir():
            local_which = shutil.which("agent-browser", path=str(local_bin_dir))
            if local_which and agent_browser_runnable(local_which):
                return True
        return False

    try:
        browser_cmd = _find_agent_browser(validate=False)
    except FileNotFoundError:
        return False
    # On Termux, the bare npx fallback is too fragile to advertise as ready —
    # require a real install, matching check_browser_requirements.
    if _requires_real_termux_browser_install(browser_cmd):
        return False
    return True


def _local_browser_runnable() -> bool:
    """Return True when the *local* browser backend would actually start.

    The ``agent-browser`` CLI being present is necessary but not sufficient for
    local mode: agent-browser also needs a Chromium build on disk (without one
    it hangs on first use until the command timeout fires), unless the
    Lightpanda engine is selected — text-only navigation needs no Chromium.

    This mirrors the local-mode tail of
    :func:`tools.browser_tool.check_browser_requirements`, so the setup/status
    surfaces advertise local browser readiness only when the runtime would
    actually run it. Cloud providers (Browserbase, Browser Use, Firecrawl) host
    their own Chromium and therefore gate on :func:`_has_agent_browser` alone.
    """
    if not _has_agent_browser():
        return False
    try:
        from tools.browser_tool import _chromium_installed, _using_lightpanda_engine
    except Exception:
        # If the runtime probe can't be imported, fall back to binary presence
        # (prior behaviour) rather than crashing the setup/status surface.
        return True
    if _using_lightpanda_engine():
        return True
    return _chromium_installed()


def _browser_label(current_provider: str) -> str:
    mapping = {
        "browserbase": "Browserbase",
        "browser-use": "Browser Use",
        "firecrawl": "Firecrawl",
        "camofox": "Camofox",
        "local": "Local browser",
    }
    return mapping.get(current_provider or "local", current_provider or "Local browser")


def _tts_label(current_provider: str) -> str:
    mapping = {
        "openai": "OpenAI TTS",
        "elevenlabs": "ElevenLabs",
        "edge": "Edge TTS",
        "xai": "xAI TTS",
        "mistral": "Mistral Voxtral TTS",
        "neutts": "NeuTTS",
    }
    return mapping.get(current_provider or "edge", current_provider or "Edge TTS")


def _stt_label(current_provider: str) -> str:
    mapping = {
        "openai": "OpenAI Whisper",
        "groq": "Groq Whisper",
        "mistral": "Mistral Voxtral Transcribe",
        "local": "Local faster-whisper",
    }
    return mapping.get(current_provider or "local", current_provider or "Local faster-whisper")


def _local_stt_backend_available() -> bool:
    """Whether a local STT backend could serve transcription right now.

    True when faster-whisper is importable or a custom local STT command
    is configured. Used both for feature detection and to stop
    ``apply_nous_managed_defaults`` from flipping a working local setup
    to the managed gateway.
    """
    if get_env_value("HERMES_LOCAL_STT_COMMAND"):
        return True
    try:
        from tools.transcription_tools import _HAS_FASTER_WHISPER

        return bool(_HAS_FASTER_WHISPER)
    except Exception:
        return False


def _resolve_browser_feature_state(
    *,
    browser_tool_enabled: bool,
    browser_provider: str,
    browser_provider_explicit: bool,
    browser_local_available: bool,
    browser_local_runnable: bool,
    direct_camofox: bool,
    direct_browserbase: bool,
    direct_browser_use: bool,
    direct_firecrawl: bool,
    managed_browser_available: bool,
) -> tuple[str, bool, bool, bool]:
    """Resolve browser availability using the same precedence as runtime.

    ``browser_local_available`` means "the agent-browser CLI is present" — the
    only local requirement for cloud providers, which host their own Chromium.
    ``browser_local_runnable`` additionally requires a usable local Chromium
    build (or the Lightpanda engine), mirroring the local-mode tail of
    :func:`tools.browser_tool.check_browser_requirements`. Local mode must gate
    on the latter, or setup/status advertise a browser that fails on first use
    when Chromium is missing.
    """
    if browser_provider_explicit:
        current_provider = browser_provider or "local"
        if current_provider == "camofox":
            # Camofox is now a stored selection (browser.cloud_provider:
            # camofox); CAMOFOX_URL is only the server address.
            available = bool(direct_camofox)
            active = bool(browser_tool_enabled and available)
            return current_provider, available, active, False
        if current_provider == "browserbase":
            available = bool(browser_local_available and direct_browserbase)
            active = bool(browser_tool_enabled and available)
            return current_provider, available, active, False
        if current_provider == "browser-use":
            provider_available = managed_browser_available or direct_browser_use
            available = bool(browser_local_available and provider_available)
            managed = bool(
                browser_tool_enabled
                and browser_local_available
                and managed_browser_available
                and not direct_browser_use
            )
            active = bool(browser_tool_enabled and available)
            return current_provider, available, active, managed
        if current_provider == "firecrawl":
            available = bool(browser_local_available and direct_firecrawl)
            active = bool(browser_tool_enabled and available)
            return current_provider, available, active, False
        if current_provider == "camofox":
            return current_provider, False, False, False

        current_provider = "local"
        available = bool(browser_local_runnable)
        active = bool(browser_tool_enabled and available)
        return current_provider, available, active, False

    # Never-configured autodetect: CAMOFOX_URL keeps activating Camofox
    # exactly as before when no cloud_provider selection was ever stored.
    if direct_camofox:
        return "camofox", True, bool(browser_tool_enabled), False

    if managed_browser_available or direct_browser_use:
        available = bool(browser_local_available)
        managed = bool(
            browser_tool_enabled
            and browser_local_available
            and managed_browser_available
            and not direct_browser_use
        )
        active = bool(browser_tool_enabled and available)
        return "browser-use", available, active, managed

    if direct_browserbase:
        available = bool(browser_local_available)
        active = bool(browser_tool_enabled and available)
        return "browserbase", available, active, False

    available = bool(browser_local_runnable)
    active = bool(browser_tool_enabled and available)
    return "local", available, active, False


def get_tool_subscription_features(
    config: Optional[Dict[str, object]] = None,
    *,
    force_fresh: bool = False,
) -> ToolSubscriptionFeatures:
    if config is None:
        config = load_config() or {}
    config = dict(config)
    model_cfg = _model_config_dict(config)
    provider_is_nous = str(model_cfg.get("provider") or "").strip().lower() == "nous"

    # Nous Portal account source removed — managed tools are never entitled.
    account_info = None

    # Coarse "entitled to any managed tool" gate: paid access OR a live free
    # tool pool. Per-backend availability is then narrowed by coverage below
    # (the pool funds image but not video, etc.).
    managed_tools_flag = bool(
        account_info
        and account_info.logged_in
        and account_info.tool_gateway_entitled
    )
    nous_auth_present = bool(account_info and account_info.logged_in)

    def _entitled_for(category: str) -> bool:
        return False
    subscribed = provider_is_nous or nous_auth_present

    web_tool_enabled = _toolset_enabled(config, "web")
    image_tool_enabled = _toolset_enabled(config, "image_gen")
    video_tool_enabled = _toolset_enabled(config, "video_gen")
    tts_tool_enabled = _toolset_enabled(config, "tts")
    browser_tool_enabled = _toolset_enabled(config, "browser")
    modal_tool_enabled = _toolset_enabled(config, "terminal")

    web_cfg = config.get("web") if isinstance(config.get("web"), dict) else {}
    tts_cfg = config.get("tts") if isinstance(config.get("tts"), dict) else {}
    stt_cfg = config.get("stt") if isinstance(config.get("stt"), dict) else {}
    browser_cfg = config.get("browser") if isinstance(config.get("browser"), dict) else {}
    terminal_cfg = config.get("terminal") if isinstance(config.get("terminal"), dict) else {}

    web_backend = str(web_cfg.get("backend") or "").strip().lower()
    # Per-capability overrides: if set, they determine which backend is active for
    # search/extract independently of web.backend.
    web_search_backend = str(web_cfg.get("search_backend") or "").strip().lower()
    tts_provider = str(tts_cfg.get("provider") or "edge").strip().lower()
    # STT default is "local" (faster-whisper) per DEFAULT_CONFIG, which
    # requires `pip install faster-whisper`. For Nous subscribers we'd
    # rather route through the managed OpenAI audio gateway — see
    # apply_nous_managed_defaults below.
    stt_provider = str(stt_cfg.get("provider") or "local").strip().lower()
    browser_provider_explicit = "cloud_provider" in browser_cfg
    browser_provider = normalize_browser_cloud_provider(
        browser_cfg.get("cloud_provider") if browser_provider_explicit else None
    )
    terminal_backend = (
        str(terminal_cfg.get("backend") or "local").strip().lower()
    )
    modal_mode = normalize_modal_mode(
        terminal_cfg.get("modal_mode")
    )

    # Stored selections (strict model): one provider string per category.
    # "nous" (stored value or legacy use_gateway: true) = managed gateway;
    # vendor name = that vendor direct; None = never configured (autodetect).
    image_gen_cfg = config.get("image_gen") if isinstance(config.get("image_gen"), dict) else {}
    video_gen_cfg = config.get("video_gen") if isinstance(config.get("video_gen"), dict) else {}
    web_selected = _selected_provider(web_cfg, "backend")
    tts_selected = _selected_provider(tts_cfg)
    stt_selected = _selected_provider(stt_cfg)
    browser_selected = _selected_provider(browser_cfg, "cloud_provider")
    image_selected = _selected_provider(image_gen_cfg)
    video_selected = _selected_provider(video_gen_cfg)

    # Lockstep with tools.tool_backend_helpers.read_selection: these are
    # merged-config sections, so the legacy DEFAULT_CONFIG-seeded
    # ``stt.provider: local`` COULD appear here without a user pick on old
    # versions. Current DEFAULT_CONFIG no longer seeds it, so a merged
    # ``local`` implies the raw file holds it — a genuine selection.

    # Managed selection flags (replace the legacy use_gateway reads —
    # use_gateway is now interpreted only inside _selected_provider).
    web_use_gateway = web_selected == "nous"
    tts_use_gateway = tts_selected == "nous"
    stt_use_gateway = stt_selected == "nous"
    browser_use_gateway = browser_selected == "nous"
    image_use_gateway = image_selected == "nous"
    video_use_gateway = video_selected == "nous"

    # The "nous" selection is serviced by a concrete vendor implementation —
    # normalize the current-provider labels so downstream vendor checks hold.
    if web_backend == "nous" or web_use_gateway:
        web_backend = "firecrawl"
    if tts_provider == "nous" or tts_use_gateway:
        tts_provider = "openai"
    if stt_provider == "nous" or stt_use_gateway:
        stt_provider = "openai"
    if browser_provider == "nous" or browser_use_gateway:
        browser_provider = "browser-use"

    direct_exa = bool(get_env_value("EXA_API_KEY"))
    direct_firecrawl = bool(get_env_value("FIRECRAWL_API_KEY") or get_env_value("FIRECRAWL_API_URL"))
    direct_parallel = bool(get_env_value("PARALLEL_API_KEY"))
    direct_tavily = bool(get_env_value("TAVILY_API_KEY"))
    direct_searxng = bool(get_env_value("SEARXNG_URL"))
    direct_fal = fal_key_is_configured()
    direct_fal_video = direct_fal  # same FAL_KEY; separate var so use_gateway is independent
    direct_openai_tts = bool(resolve_openai_audio_api_key())
    direct_elevenlabs = bool(get_env_value("ELEVENLABS_API_KEY"))
    direct_camofox = bool(get_env_value("CAMOFOX_URL"))
    direct_browserbase = bool(get_env_value("BROWSERBASE_API_KEY") and get_env_value("BROWSERBASE_PROJECT_ID"))
    direct_browser_use = bool(get_env_value("BROWSER_USE_API_KEY"))
    direct_modal = has_direct_modal_credentials()

    # STT direct providers. OpenAI Whisper reuses the same audio key as
    # OpenAI TTS — resolve_openai_audio_api_key() reads VOICE_TOOLS_OPENAI_KEY
    # and falls back to OPENAI_API_KEY. The local provider's "direct"
    # signal is whether faster-whisper is importable; we lazy-import so
    # this module stays cheap on the happy path.
    direct_openai_stt = bool(resolve_openai_audio_api_key())
    direct_groq_stt = bool(get_env_value("GROQ_API_KEY"))
    direct_mistral_stt = bool(get_env_value("MISTRAL_API_KEY"))
    try:
        from tools.transcription_tools import _HAS_FASTER_WHISPER
        local_stt_available = bool(_HAS_FASTER_WHISPER) or bool(
            get_env_value("HERMES_LOCAL_STT_COMMAND")
        )
    except Exception:
        local_stt_available = bool(get_env_value("HERMES_LOCAL_STT_COMMAND"))

    # When use_gateway is set, suppress direct credentials for managed detection
    if web_use_gateway:
        direct_firecrawl = False
        direct_exa = False
        direct_parallel = False
        direct_tavily = False
    if image_use_gateway:
        direct_fal = False
    if video_use_gateway:
        direct_fal_video = False
    if tts_use_gateway:
        direct_openai_tts = False
        direct_elevenlabs = False
    if stt_use_gateway:
        direct_openai_stt = False
        direct_groq_stt = False
        direct_mistral_stt = False
        local_stt_available = False
    if browser_use_gateway:
        direct_browser_use = False
        direct_browserbase = False

    managed_web_available = (
        managed_tools_flag
        and nous_auth_present
        and is_managed_tool_gateway_ready("firecrawl")
        and _entitled_for("firecrawl")
    )
    managed_image_available = (
        managed_tools_flag
        and nous_auth_present
        and is_managed_tool_gateway_ready("fal-queue")
        and _entitled_for("fal")
    )
    # Video gen rides the same fal-queue gateway as image gen, but the free tool
    # pool funds image and NOT video — so gate it on its own coverage category
    # rather than aliasing it to image. (Paid users are entitled to both.)
    managed_video_available = (
        managed_tools_flag
        and nous_auth_present
        and is_managed_tool_gateway_ready("fal-queue")
        and _entitled_for("fal-video")
    )
    managed_tts_available = (
        managed_tools_flag
        and nous_auth_present
        and is_managed_tool_gateway_ready("openai-audio")
        and _entitled_for("openai-audio")
    )
    # STT and TTS share the same managed gateway endpoint ("openai-audio")
    # because the OpenAI audio API covers both /audio/speech (TTS) and
    # /audio/transcriptions (STT). One probe (and one entitlement), used by both.
    managed_stt_available = managed_tts_available
    managed_browser_available = (
        managed_tools_flag
        and nous_auth_present
        and is_managed_tool_gateway_ready("browser-use")
        and _entitled_for("browser-use")
    )
    managed_modal_available = (
        managed_tools_flag
        and nous_auth_present
        and is_managed_tool_gateway_ready("modal")
        and _entitled_for("modal")
    )
    modal_state = resolve_modal_backend_state(
        modal_mode,
        has_direct=direct_modal,
        managed_ready=managed_modal_available,
        managed_enabled=managed_tools_flag,
    )

    # Strict selection: a stored VENDOR selection pins the category to direct
    # credentials — managed availability must not light the feature up (the
    # runtime will error, not reroute), and camofox/local selections must not
    # be pre-empted by env credentials for other providers.
    if web_selected is not None and not web_use_gateway:
        managed_web_available = False
    if image_selected is not None and not image_use_gateway:
        managed_image_available = False
    if video_selected is not None and not video_use_gateway:
        managed_video_available = False
    if tts_selected is not None and not tts_use_gateway:
        managed_tts_available = False
    if stt_selected is not None and not stt_use_gateway:
        managed_stt_available = False
    if browser_selected is not None and not browser_use_gateway:
        managed_browser_available = False
    if browser_selected is not None and browser_selected != "camofox":
        # CAMOFOX_URL is the server address, not a selection: an explicit
        # different browser choice wins over the env var.
        direct_camofox = False

    web_managed = web_backend == "firecrawl" and managed_web_available and not direct_firecrawl
    web_active = bool(
        web_tool_enabled
        and (
            web_managed
            or (web_backend == "exa" and direct_exa)
            or (web_backend == "firecrawl" and direct_firecrawl)
            or (web_backend == "parallel" and direct_parallel)
            or (web_backend == "tavily" and direct_tavily)
            or (web_backend == "searxng" and direct_searxng)
            # Per-capability overrides: search_backend or extract_backend may be set
            # without web.backend (using the new split config from #20061)
            or (web_search_backend == "searxng" and direct_searxng)
            or (web_search_backend == "exa" and direct_exa)
            or (web_search_backend == "firecrawl" and direct_firecrawl)
            or (web_search_backend == "parallel" and direct_parallel)
            or (web_search_backend == "tavily" and direct_tavily)
        )
    )
    web_available = bool(
        managed_web_available or direct_exa or direct_firecrawl or direct_parallel or direct_tavily or direct_searxng
    )

    image_managed = image_tool_enabled and managed_image_available and not direct_fal
    image_active = bool(image_tool_enabled and (image_managed or direct_fal))
    image_available = bool(managed_image_available or direct_fal)

    video_managed = video_tool_enabled and managed_video_available and not direct_fal_video
    video_active = bool(video_tool_enabled and (video_managed or direct_fal_video))
    video_available = bool(managed_video_available or direct_fal_video)

    tts_current_provider = tts_provider or "edge"
    tts_managed = (
        tts_tool_enabled
        and tts_current_provider == "openai"
        and managed_tts_available
        and not direct_openai_tts
    )
    tts_available = bool(
        tts_current_provider in {"edge", "neutts"}
        or (tts_current_provider == "openai" and (managed_tts_available or direct_openai_tts))
        or (tts_current_provider == "elevenlabs" and direct_elevenlabs)
        or (tts_current_provider == "mistral" and bool(get_env_value("MISTRAL_API_KEY")))
    )
    tts_active = bool(tts_tool_enabled and tts_available)

    # STT availability per provider. Unlike TTS, STT isn't a model-callable
    # tool — the gateway voice middleware calls it on every inbound voice
    # message — so toolset_enabled is N/A and we treat stt as always
    # "enabled" if a usable provider is configured.
    stt_current_provider = stt_provider or "local"
    stt_managed = (
        stt_current_provider == "openai"
        and managed_stt_available
        and not direct_openai_stt
    )
    stt_available = bool(
        (stt_current_provider == "local" and local_stt_available)
        or (stt_current_provider == "openai" and (managed_stt_available or direct_openai_stt))
        or (stt_current_provider == "groq" and direct_groq_stt)
        or (stt_current_provider == "mistral" and direct_mistral_stt)
    )
    stt_active = stt_available

    browser_local_available = _has_agent_browser()
    browser_local_runnable = _local_browser_runnable()
    (
        browser_current_provider,
        browser_available,
        browser_active,
        browser_managed,
    ) = _resolve_browser_feature_state(
        browser_tool_enabled=browser_tool_enabled,
        browser_provider=browser_provider,
        browser_provider_explicit=browser_provider_explicit,
        browser_local_available=browser_local_available,
        browser_local_runnable=browser_local_runnable,
        direct_camofox=direct_camofox,
        direct_browserbase=direct_browserbase,
        direct_browser_use=direct_browser_use,
        direct_firecrawl=direct_firecrawl,
        managed_browser_available=managed_browser_available,
    )

    if terminal_backend != "modal":
        modal_managed = False
        modal_available = True
        modal_active = bool(modal_tool_enabled)
        modal_direct_override = False
    elif modal_state["selected_backend"] == "managed":
        modal_managed = bool(modal_tool_enabled)
        modal_available = True
        modal_active = bool(modal_tool_enabled)
        modal_direct_override = False
    elif modal_state["selected_backend"] == "direct":
        modal_managed = False
        modal_available = True
        modal_active = bool(modal_tool_enabled)
        modal_direct_override = bool(modal_tool_enabled)
    elif modal_mode == "managed":
        modal_managed = False
        modal_available = bool(managed_modal_available)
        modal_active = False
        modal_direct_override = False
    elif modal_mode == "direct":
        modal_managed = False
        modal_available = bool(direct_modal)
        modal_active = False
        modal_direct_override = False
    else:
        modal_managed = False
        modal_available = bool(managed_modal_available or direct_modal)
        modal_active = False
        modal_direct_override = False

    # Explicit-configured mirrors the stored selections computed above so
    # status/picker markers stay in lockstep with runtime dispatch.
    tts_explicit_configured = tts_selected is not None and tts_selected != "edge"
    stt_explicit_configured = stt_selected is not None

    features = {
        "web": ToolFeatureState(
            key="web",
            label="Web tools",
            included_by_default=True,
            available=web_available,
            active=web_active,
            managed_by_nous=web_managed,
            direct_override=web_active and not web_managed,
            toolset_enabled=web_tool_enabled,
            current_provider=web_backend or web_search_backend or "",
            explicit_configured=bool(web_backend or web_search_backend),
        ),
        "image_gen": ToolFeatureState(
            key="image_gen",
            label="Image generation",
            included_by_default=True,
            available=image_available,
            active=image_active,
            managed_by_nous=image_managed,
            direct_override=image_active and not image_managed,
            toolset_enabled=image_tool_enabled,
            current_provider="FAL" if (image_selected not in (None, "nous") or (image_selected is None and direct_fal)) else ("Nous Subscription" if (image_managed or image_use_gateway) else ""),
            explicit_configured=image_selected is not None or direct_fal,
        ),
        "video_gen": ToolFeatureState(
            key="video_gen",
            label="Video generation",
            included_by_default=False,
            available=video_available,
            active=video_active,
            managed_by_nous=video_managed,
            direct_override=video_active and not video_managed,
            toolset_enabled=video_tool_enabled,
            current_provider="FAL" if (video_selected not in (None, "nous") or (video_selected is None and direct_fal_video)) else ("Nous Subscription" if (video_managed or video_use_gateway) else ""),
            explicit_configured=video_selected is not None or direct_fal_video,
        ),
        "tts": ToolFeatureState(
            key="tts",
            label="OpenAI TTS",
            included_by_default=True,
            available=tts_available,
            active=tts_active,
            managed_by_nous=tts_managed,
            direct_override=tts_active and not tts_managed,
            toolset_enabled=tts_tool_enabled,
            current_provider=_tts_label(tts_current_provider),
            explicit_configured=tts_explicit_configured,
        ),
        "stt": ToolFeatureState(
            key="stt",
            label="Speech-to-text",
            included_by_default=True,
            available=stt_available,
            active=stt_active,
            managed_by_nous=stt_managed,
            direct_override=stt_active and not stt_managed,
            # STT isn't toolset-gated (gateway middleware calls it
            # unconditionally on inbound voice), so report True so the
            # status display doesn't flag it as "tool disabled".
            toolset_enabled=True,
            current_provider=_stt_label(stt_current_provider),
            explicit_configured=stt_explicit_configured,
        ),
        "browser": ToolFeatureState(
            key="browser",
            label="Browser automation",
            included_by_default=True,
            available=browser_available,
            active=browser_active,
            managed_by_nous=browser_managed,
            direct_override=browser_active and not browser_managed,
            toolset_enabled=browser_tool_enabled,
            current_provider=_browser_label(browser_current_provider),
            explicit_configured=browser_provider_explicit,
        ),
        "modal": ToolFeatureState(
            key="modal",
            label="Modal execution",
            included_by_default=False,
            available=modal_available,
            active=modal_active,
            managed_by_nous=modal_managed,
            direct_override=terminal_backend == "modal" and modal_direct_override,
            toolset_enabled=modal_tool_enabled,
            current_provider="Modal" if terminal_backend == "modal" else terminal_backend or "local",
            explicit_configured=terminal_backend == "modal",
        ),
    }

    return ToolSubscriptionFeatures(
        subscribed=subscribed,
        nous_auth_present=nous_auth_present,
        provider_is_nous=provider_is_nous,
        features=features,
        account_info=account_info,
    )
