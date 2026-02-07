"""AI configuration commands."""

import typer

from ..core.models import AIProviderType, Language
from ..services.providers import PROVIDERS, get_provider
from ..services.settings_service import SettingsService
from ..utils.display import console, print_error, print_info, print_success

app = typer.Typer(
    help="AI provider configuration",
    no_args_is_help=False,
    invoke_without_command=True,
)


@app.callback()
def config_callback(ctx: typer.Context):
    """AI configuration — shows current settings when run without subcommand."""
    if ctx.invoked_subcommand is None:
        show()


@app.command("show")
def show():
    """Show current AI settings."""
    settings = SettingsService()
    all_settings = settings.get_all()

    console.print("[bold]AI Configuration[/bold]")
    console.print()
    console.print(f"  Provider : [cyan]{all_settings['ai_provider']}[/cyan]")
    model_display = all_settings["ai_model"] or "(default)"
    console.print(f"  Model    : [cyan]{model_display}[/cyan]")
    console.print(f"  Timeout  : [cyan]{all_settings['ai_timeout']}s[/cyan]")
    lang_display = all_settings.get("language", "en")
    console.print(f"  Language : [cyan]{lang_display}[/cyan]")
    if all_settings["ai_provider"] == AIProviderType.CUSTOM.value:
        cmd_display = all_settings.get("custom_command") or "(not set)"
        console.print(f"  Command  : [cyan]{cmd_display}[/cyan]")

    console.print()
    console.print("[bold]Available Providers[/bold]")
    for ptype in PROVIDERS:
        provider = get_provider(ptype)
        available = provider.is_available()
        status = "[green]available[/green]" if available else "[red]not found[/red]"
        current = (
            " [yellow]← current[/yellow]" if ptype.value == all_settings["ai_provider"] else ""
        )
        cli_name = provider.cli_command or "(not set)"
        console.print(f"  {ptype.value:8s} ({cli_name}) {status}{current}")


@app.command("set-provider")
def set_provider(
    name: str = typer.Argument(
        ..., help="Provider name (gemini, claude, openai, ollama, opencode, custom)"
    ),
):
    """Change AI provider."""
    try:
        provider_type = AIProviderType(name.lower())
    except ValueError:
        valid = ", ".join(p.value for p in AIProviderType)
        print_error(f"Unknown provider: {name}. Valid: {valid}")
        raise typer.Exit(1) from None

    settings = SettingsService()
    if provider_type == AIProviderType.CUSTOM and not settings.get("custom_command"):
        print_error("No custom command configured. Use 'axp config set-custom' first")
        raise typer.Exit(1)

    provider = get_provider(provider_type)
    if not provider.is_available():
        print_info(f"Warning: '{provider.cli_command}' not found on PATH")

    settings.set("ai_provider", provider_type.value)
    print_success(f"Provider set to: {provider_type.value}")


@app.command("set-model")
def set_model(
    name: str = typer.Argument(..., help="Model name (use 'default' to reset)"),
):
    """Set AI model override."""
    settings = SettingsService()
    if name.lower() == "default":
        settings.set("ai_model", "")
        print_success("Model reset to provider default")
    else:
        settings.set("ai_model", name)
        print_success(f"Model set to: {name}")


@app.command("set-timeout")
def set_timeout(
    seconds: int = typer.Argument(..., help="Timeout in seconds (10-300)"),
):
    """Set AI request timeout."""
    if not 10 <= seconds <= 300:
        print_error("Timeout must be between 10 and 300 seconds")
        raise typer.Exit(1)

    settings = SettingsService()
    settings.set("ai_timeout", str(seconds))
    print_success(f"Timeout set to: {seconds}s")


@app.command("set-language")
def set_language(
    lang: str = typer.Argument(..., help="Language code (en, ko)"),
):
    """Change display language."""
    try:
        language = Language(lang.lower())
    except ValueError:
        valid = ", ".join(lang_.value for lang_ in Language)
        print_error(f"Unknown language: {lang}. Valid: {valid}")
        raise typer.Exit(1) from None

    settings = SettingsService()
    settings.set("language", language.value)
    print_success(f"Language set to: {language.value}")


@app.command("set-custom")
def set_custom(
    template: str = typer.Argument(..., help="Command template (e.g. 'my-ai --prompt {prompt}')"),
):
    """Set custom AI command template.

    Template must contain a {prompt} placeholder. {model} is optional.
    Example: axp config set-custom "my-ai -m {model} -p {prompt}"
    """
    if "{prompt}" not in template:
        print_error("Template must contain {prompt} placeholder")
        raise typer.Exit(1)

    settings = SettingsService()
    settings.set("custom_command", template)
    print_success(f"Custom command set: {template}")
    if settings.get("ai_provider") != AIProviderType.CUSTOM.value:
        print_info("Tip: run 'axp config set-provider custom' to activate")


@app.command("test")
def test():
    """Test current provider connection."""
    settings = SettingsService()
    provider_type = settings.get_provider()
    provider = get_provider(provider_type)

    if provider_type == AIProviderType.CUSTOM and not provider.cli_command:
        print_error("No custom command configured. Use 'axp config set-custom' first")
        raise typer.Exit(1)

    console.print(f"Testing [cyan]{provider_type.value}[/cyan] ({provider.cli_command})...")

    if not provider.is_available():
        print_error(f"'{provider.cli_command}' not found on PATH")
        raise typer.Exit(1)

    output = provider.invoke(
        "Say 'hello' in one word.",
        model=settings.get_model(),
        timeout=settings.get_timeout(),
    )
    if output:
        print_success(f"Response: {output[:200]}")
    else:
        print_error("No response received")
        raise typer.Exit(1)
