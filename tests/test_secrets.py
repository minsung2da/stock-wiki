"""Tests for secret management hygiene (OPS-06).

Validates:
- .env.example exists with required placeholder keys
- python-dotenv can parse .env.example
- .gitignore excludes .env files
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


class TestSecretManagement:
    def test_env_example_exists(self) -> None:
        """.env.example template file exists."""
        env_example = PROJECT_ROOT / ".env.example"
        assert env_example.exists(), ".env.example must exist at project root"

    def test_env_example_has_required_keys(self) -> None:
        """.env.example contains all required environment variable placeholders."""
        env_example = PROJECT_ROOT / ".env.example"
        content = env_example.read_text(encoding="utf-8")
        required_keys = [
            "OPEN_DART_API_KEY",
            "POSTGRES_PASSWORD",
            "DATABASE_URL",
            "FRED_API_KEY",
            "ECOS_API_KEY",
        ]
        for key in required_keys:
            assert key in content, f".env.example must contain {key}"

    def test_dotenv_loads_env_example(self) -> None:
        """python-dotenv can load .env.example without errors."""
        from dotenv import dotenv_values

        env_example = PROJECT_ROOT / ".env.example"
        values = dotenv_values(str(env_example))
        assert "OPEN_DART_API_KEY" in values
        assert values["OPEN_DART_API_KEY"] is not None

    def test_gitignore_excludes_env(self) -> None:
        """.gitignore contains .env exclusion pattern."""
        gitignore = PROJECT_ROOT / ".gitignore"
        content = gitignore.read_text(encoding="utf-8")
        assert ".env" in content, ".gitignore must exclude .env files"

    def test_gitignore_excludes_private(self) -> None:
        """.gitignore contains notes/private/ exclusion (per D-03)."""
        gitignore = PROJECT_ROOT / ".gitignore"
        content = gitignore.read_text(encoding="utf-8")
        assert "notes/private/" in content, (
            ".gitignore must exclude notes/private/ for portfolio privacy"
        )
