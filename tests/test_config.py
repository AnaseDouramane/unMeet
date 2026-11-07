import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_setting(tmp_path: Path, expression: str, env: dict[str, str] | None = None) -> str:
    process_env = {
        key: value for key, value in os.environ.items() if key not in {"HACKERNEWS_LIMIT"}
    }
    process_env["PYTHONPATH"] = str(PROJECT_ROOT)
    process_env.update(env or {})
    result = subprocess.run(
        [sys.executable, "-c", f"from app.config import settings; print({expression})"],
        cwd=tmp_path,
        env=process_env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def test_settings_load_values_from_dotenv_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("HACKERNEWS_LIMIT=42\n", encoding="utf-8")

    assert _read_setting(tmp_path, "settings.hackernews_limit") == "42"


def test_process_environment_overrides_dotenv_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("HACKERNEWS_LIMIT=42\n", encoding="utf-8")

    value = _read_setting(tmp_path, "settings.hackernews_limit", {"HACKERNEWS_LIMIT": "7"})

    assert value == "7"
