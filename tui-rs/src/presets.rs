/// Built-in provider presets for custom provider creation.
pub struct Preset {
    pub name: &'static str,
    pub description: &'static str,
    /// Template with `{name}`, `{prompt}`, `{model}` placeholders.
    pub template: &'static str,
}

pub const PRESETS: &[Preset] = &[
    Preset {
        name: "Claude-like",
        description: "CLI with -p/--model/--output-format (e.g. zai, claude)",
        template: "{name} -p {prompt} --model {model} --output-format text",
    },
    Preset {
        name: "Codex-like",
        description: "CLI with --prompt/--model (e.g. codex)",
        template: "{name} --model {model} --prompt {prompt}",
    },
    Preset {
        name: "Gemini-like",
        description: "CLI with -p/-m (e.g. gemini)",
        template: "{name} -m {model} -p {prompt}",
    },
    Preset {
        name: "Ollama-like",
        description: "CLI with run subcommand (e.g. ollama)",
        template: "{name} run {model} {prompt}",
    },
    Preset {
        name: "OpenRouter",
        description: "HTTP API via curl ($OPENROUTER_API_KEY env var)",
        template: "curl -sS https://openrouter.ai/api/v1/chat/completions -H \"Content-Type: application/json\" -H \"Authorization: Bearer $OPENROUTER_API_KEY\" -d '{{\"model\":\"{model}\",\"messages\":[{{\"role\":\"user\",\"content\":\"{prompt}\"}}]}}'",
    },
    Preset {
        name: "Manual",
        description: "Write the full command yourself",
        template: "{name} {prompt}",
    },
];

/// Reserved names that cannot be used for custom providers.
pub const RESERVED: &[&str] = &["gemini", "claude", "ollama", "openai", "opencode", "custom"];

pub fn is_reserved(name: &str) -> bool {
    RESERVED.iter().any(|&r| r.eq_ignore_ascii_case(name))
}
