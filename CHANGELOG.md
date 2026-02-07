# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-06-01

### Added

- Personalized paper recommendations using TF-IDF content similarity, category matching, keyword matching, and recency scoring
- CLI interface (`axp`) with commands for daily papers, search, preferences, reading lists, notes, and export
- TUI interface (`axp tui`) with five tabs: Daily, Search, Lists, Notes, Prefs
- AI-powered summarization and translation via pluggable providers (Gemini, Claude, Codex, Ollama, OpenCode, custom)
- Reading list management with status tracking (unread, reading, completed)
- Paper notes with typed categories (general, question, insight, todo)
- Export to Markdown, JSON, and CSV formats
- SQLite-backed paper cache to reduce arXiv API calls
- Integration with [arxivterminal](https://github.com/Axect/arxivterminal) (read-only) and [arxiv-doc-builder](https://github.com/Axect/arxiv-doc-builder)
- Multi-language support (English, Korean)

[0.1.0]: https://github.com/Axect/arXiv_explorer/releases/tag/v0.1.0
