"""AI provider abstraction."""

import shlex
import shutil
import subprocess
from abc import ABC, abstractmethod

from ..core.models import AIProviderType


class AIProvider(ABC):
    """AI CLI provider base class."""

    @property
    @abstractmethod
    def provider_type(self) -> AIProviderType: ...

    @property
    @abstractmethod
    def cli_command(self) -> str: ...

    @property
    @abstractmethod
    def default_model(self) -> str: ...

    @abstractmethod
    def build_command(self, prompt: str, model: str = "") -> list[str]: ...

    def is_available(self) -> bool:
        """Check if the CLI is on the PATH."""
        return shutil.which(self.cli_command) is not None

    def invoke(self, prompt: str, model: str = "", timeout: int = 120) -> str | None:
        """Run the CLI and return stdout. Returns None on failure."""
        if not self.is_available():
            return None
        cmd = self.build_command(prompt, model)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                return None
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, Exception):
            return None


class GeminiProvider(AIProvider):
    provider_type = AIProviderType.GEMINI
    cli_command = "gemini"
    default_model = ""

    def build_command(self, prompt: str, model: str = "") -> list[str]:
        cmd = [self.cli_command]
        effective_model = model or self.default_model
        if effective_model:
            cmd += ["-m", effective_model]
        cmd += ["-p", prompt]
        return cmd


class ClaudeProvider(AIProvider):
    provider_type = AIProviderType.CLAUDE
    cli_command = "claude"
    default_model = ""

    def build_command(self, prompt: str, model: str = "") -> list[str]:
        cmd = [self.cli_command]
        effective_model = model or self.default_model
        if effective_model:
            cmd += ["--model", effective_model]
        cmd += ["-p", prompt, "--output-format", "text"]
        return cmd


class CodexProvider(AIProvider):
    """OpenAI provider via the openai-codex Python SDK.

    Drives the local Codex app-server through the SDK, reusing the user's
    existing Codex/ChatGPT auth (``~/.codex``), so it needs neither an
    ``OPENAI_API_KEY`` nor a ``codex`` binary on PATH. The SDK bundles its
    own pinned runtime.
    """

    provider_type = AIProviderType.OPENAI
    cli_command = "codex"  # informational only; not used for dispatch
    default_model = ""

    def build_command(self, prompt: str, model: str = "") -> list[str]:
        # Unused: this provider talks to Codex over the SDK, not a subprocess.
        return []

    def is_available(self) -> bool:
        """Available when the SDK is importable (auth is checked at invoke)."""
        try:
            import openai_codex  # noqa: F401
        except ImportError:
            return False
        return True

    def invoke(self, prompt: str, model: str = "", timeout: int = 120) -> str | None:
        """Run a single Codex turn and return its final text response.

        Runs read-only in a temp working directory so the coding agent
        cannot touch the project. ``timeout`` is accepted for interface
        parity but the SDK manages its own app-server lifecycle.
        """
        import tempfile

        try:
            from openai_codex import Codex, Sandbox
        except ImportError:
            return None

        effective_model = model or self.default_model
        run_kwargs: dict = {"sandbox": Sandbox.read_only, "cwd": tempfile.gettempdir()}
        if effective_model:
            run_kwargs["model"] = effective_model
        # These are single-shot text tasks (summaries, translations, review
        # sections), not agentic coding, so cap reasoning effort low to keep
        # latency reasonable. Default effort can take minutes per call.
        try:
            from openai_codex.api import ReasoningEffort

            run_kwargs["effort"] = ReasoningEffort.low
        except Exception:
            pass

        try:
            with Codex() as codex:
                thread = codex.thread_start()
                result = thread.run(prompt, **run_kwargs)
                text = (getattr(result, "final_response", "") or "").strip()
                return text or None
        except Exception:
            return None


class OllamaProvider(AIProvider):
    provider_type = AIProviderType.OLLAMA
    cli_command = "ollama"
    default_model = "llama3.2"

    def build_command(self, prompt: str, model: str = "") -> list[str]:
        effective_model = model or self.default_model
        return [self.cli_command, "run", effective_model, prompt]


class OpencodeProvider(AIProvider):
    """OpenCode CLI provider."""

    provider_type = AIProviderType.OPENCODE
    cli_command = "opencode"
    default_model = ""

    def build_command(self, prompt: str, model: str = "") -> list[str]:
        cmd = [self.cli_command, "run"]
        effective_model = model or self.default_model
        if effective_model:
            cmd += ["--model", effective_model]
        cmd += [prompt]
        return cmd


class CustomProvider(AIProvider):
    """Custom CLI template provider."""

    provider_type = AIProviderType.CUSTOM
    cli_command = ""
    default_model = ""

    def __init__(self) -> None:
        self._template = ""

    def configure(self, template: str) -> None:
        """Load template from settings."""
        self._template = template
        tokens = shlex.split(template) if template else []
        self.cli_command = tokens[0] if tokens else ""

    def build_command(self, prompt: str, model: str = "") -> list[str]:
        if not self._template:
            return []
        effective_model = model or self.default_model
        tokens = shlex.split(self._template)
        result = []
        for token in tokens:
            replaced = token.replace("{prompt}", prompt)
            if effective_model:
                replaced = replaced.replace("{model}", effective_model)
            else:
                replaced = replaced.replace("{model}", "")
            if not replaced:
                # Drop the preceding flag (e.g. --model) when its value placeholder is empty
                if result and result[-1].startswith("-"):
                    result.pop()
                continue
            result.append(replaced)
        return result


PROVIDERS: dict[AIProviderType, AIProvider] = {
    AIProviderType.GEMINI: GeminiProvider(),
    AIProviderType.CLAUDE: ClaudeProvider(),
    AIProviderType.OPENAI: CodexProvider(),
    AIProviderType.OLLAMA: OllamaProvider(),
    AIProviderType.OPENCODE: OpencodeProvider(),
    AIProviderType.CUSTOM: CustomProvider(),
}


def get_provider(provider_name: str | AIProviderType) -> AIProvider:
    """Return a provider instance. Checks built-in registry first, then custom_providers table."""
    # Normalize to string
    name = provider_name.value if isinstance(provider_name, AIProviderType) else provider_name

    # Try built-in registry
    for ptype, prov in PROVIDERS.items():
        if ptype.value == name:
            if ptype == AIProviderType.CUSTOM:
                from .settings_service import SettingsService

                template = SettingsService().get("custom_command")
                prov.configure(template)
            return prov

    # Try custom_providers table
    from .settings_service import SettingsService

    for cp in SettingsService().get_custom_providers():
        if cp.name == name:
            provider = CustomProvider()
            provider.configure(cp.command_template)
            provider.default_model = cp.default_model
            return provider

    # Fallback to gemini
    return PROVIDERS[AIProviderType.GEMINI]
