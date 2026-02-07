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
    """OpenAI provider via Codex CLI."""

    provider_type = AIProviderType.OPENAI
    cli_command = "codex"
    default_model = ""

    def build_command(self, prompt: str, model: str = "") -> list[str]:
        cmd = [self.cli_command]
        effective_model = model or self.default_model
        if effective_model:
            cmd += ["--model", effective_model]
        cmd += ["--prompt", prompt]
        return cmd


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
        tokens = shlex.split(self._template)
        result = []
        for token in tokens:
            replaced = token.replace("{prompt}", prompt)
            if model:
                replaced = replaced.replace("{model}", model)
            else:
                replaced = replaced.replace("{model}", "")
            if replaced:
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


def get_provider(provider_type: AIProviderType) -> AIProvider:
    """Return a provider instance. If custom, load the template from settings."""
    provider = PROVIDERS[provider_type]
    if provider_type == AIProviderType.CUSTOM:
        from .settings_service import SettingsService

        template = SettingsService().get("custom_command")
        provider.configure(template)
    return provider
