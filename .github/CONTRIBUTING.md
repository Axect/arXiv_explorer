# Contributing to arXiv Explorer

Thank you for your interest in contributing to arXiv Explorer! This guide will help you get started.

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** - Fast Python package manager
- **git**

## Getting Started

1. Fork the repository and clone your fork:

   ```bash
   git clone https://github.com/<your-username>/arXiv_explorer.git
   cd arXiv_explorer
   ```

2. Install dependencies:

   ```bash
   uv sync
   ```

3. Verify the installation:

   ```bash
   uv run axp --help
   ```

## Development Workflow

### Git Workflow

This project follows **gitflow**:

- **`main`** contains stable releases only.
- **`dev`** is the active development branch.
- All feature branches should be created from `dev`.
- All pull requests should target `dev`.

To start working on a change:

```bash
git checkout dev
git pull origin dev
git checkout -b feature/your-feature-name
```

### Code Style

We use [Ruff](https://docs.astral.sh/ruff/) for both linting and formatting. Before submitting a pull request, make sure your code passes both checks:

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

### Testing

Run the full test suite with coverage:

```bash
uv run pytest --cov
```

To run a specific test file:

```bash
uv run pytest tests/test_recommendation.py
```

All new features should include tests. Aim to maintain or improve code coverage.

### Commit Messages

Write clear, descriptive commit messages that explain **why** the change was made, not just what was changed. Use the imperative mood in the subject line (e.g., "Add keyword weighting to recommendation engine" rather than "Added keyword weighting").

## Pull Request Process

1. **Ensure all tests pass** before submitting your PR.
2. **Ensure linting passes** with `uv run ruff check src/ tests/`.
3. **Describe your changes** clearly in the PR description --- what was changed, why, and how to test it.
4. **Target the `dev` branch** --- PRs to `main` will not be accepted unless they are release merges.
5. **Keep PRs focused** --- one feature or fix per pull request makes review easier.

## Reporting Issues

If you find a bug or have a feature request, please open an issue using the appropriate template. Provide as much detail as possible to help us understand and reproduce the problem.

## Questions?

If you have questions about contributing, feel free to open a discussion or reach out to the maintainer at axect.tg@proton.me.
