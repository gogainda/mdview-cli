import json
import os
from pathlib import Path

from platformdirs import user_config_path, user_data_path


def config_dir() -> Path:
    override = os.environ.get("MDVIEW_CONFIG_DIR")
    return Path(override) if override else user_config_path("mdview-cli")


def data_dir() -> Path:
    override = os.environ.get("MDVIEW_DATA_DIR")
    return Path(override) if override else user_data_path("mdview-cli")


def keys_path() -> Path:
    return config_dir() / "keys.json"


def base_url() -> str:
    return os.environ.get("MDVIEW_BASE_URL", "https://mdview.io").rstrip("/")


def get_token() -> str | None:
    value = os.environ.get("MDVIEW_TOKEN")
    if value:
        return value.strip()
    try:
        return json.loads(keys_path().read_text(encoding="utf-8")).get("default")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def save_token(token: str) -> None:
    path = keys_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"default": token}) + "\n", encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o600)


def remove_token() -> bool:
    try:
        keys_path().unlink()
        return True
    except FileNotFoundError:
        return False
