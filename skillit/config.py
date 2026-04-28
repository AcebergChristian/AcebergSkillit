import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class RuntimeConfig:
    skills_dir: Path = Path("skills")
    sessions_dir: Path = Path("sessions")
    output_dir: Path = Path("output")
    soul_file: Path = Path("soul.md")
    short_term_turns: int = 8
    max_context_chars: int = 7000
    max_memory_items: int = 2000
    max_tool_output_chars: int = 2000


CONFIG_ENV_KEYS = {
    "api-key": "SKILLIT_API_KEY",
    "base-url": "SKILLIT_BASE_URL",
    "model": "SKILLIT_MODEL",
    "api-style": "SKILLIT_API_STYLE",
    "timeout": "SKILLIT_TIMEOUT_SEC",
}


def load_dotenv(dotenv_path: Path | None = None) -> Path | None:
    path = dotenv_path or Path(".env")
    if not path.exists() or not path.is_file():
        return None

    try:
        env_map = parse_dotenv(path)
    except OSError:
        return None

    for key, value in env_map.items():
        if not key or key in os.environ:
            continue
        os.environ[key] = value
    return path


def parse_dotenv(dotenv_path: Path | None = None) -> dict[str, str]:
    path = dotenv_path or Path(".env")
    if not path.exists() or not path.is_file():
        return {}

    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _unquote_env_value(value.strip())
        if key:
            out[key] = value
    return out


def set_dotenv_value(key: str, value: str, dotenv_path: Path | None = None) -> Path:
    path = dotenv_path or Path(".env")
    env_map = parse_dotenv(path)
    env_map[key] = value
    write_dotenv(env_map, path)
    os.environ[key] = value
    return path


def get_dotenv_value(key: str, dotenv_path: Path | None = None) -> str:
    env_map = parse_dotenv(dotenv_path)
    return env_map.get(key, "")


def write_dotenv(env_map: dict[str, str], dotenv_path: Path | None = None) -> Path:
    path = dotenv_path or Path(".env")
    lines = [
        "# Managed by SkillIt config commands.",
        "# You can edit this file manually if needed.",
        "",
    ]
    for key in sorted(env_map):
        lines.append(f'{key}="{_escape_env_value(env_map[key])}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def resolve_config_key(alias: str) -> str:
    key = alias.strip().lower()
    if key in CONFIG_ENV_KEYS:
        return CONFIG_ENV_KEYS[key]
    if key.upper() in CONFIG_ENV_KEYS.values():
        return key.upper()
    raise KeyError(alias)


def _unquote_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _escape_env_value(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')
