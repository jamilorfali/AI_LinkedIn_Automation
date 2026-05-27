import os
from pathlib import Path
from typing import Dict, Any
from dataclasses import dataclass, fields

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


def _parse_scalar(value: str):
    lower = value.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    if lower in {"null", "~"}:
        return None
    if value.startswith(('"', "'")) and value.endswith(('"', "'")):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _load_simple_yaml(text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    stack = [( -1, result)]
    last_key = None

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.lstrip(" ")

        while len(stack) > 1 and indent <= stack[-1][0]:
            if isinstance(stack[-1][1], list) and stripped.startswith("- ") and indent == stack[-1][0]:
                break
            stack.pop()

        parent = stack[-1][1]

        if stripped.startswith("- "):
            item = stripped[2:]
            if not isinstance(parent, list):
                if last_key is None:
                    raise ValueError("List item without parent key")

                target_parent = parent
                if last_key not in target_parent:
                    for _, possible_parent in reversed(stack[:-1]):
                        if isinstance(possible_parent, dict) and last_key in possible_parent:
                            target_parent = possible_parent
                            break

                new_list: list = []
                target_parent[last_key] = new_list
                parent = new_list
                stack.append((indent, parent))

            if item == "":
                node: Any = {}
                parent.append(node)
                stack.append((indent + 2, node))
            elif ": " in item or item.endswith(":"):
                key, _, remainder = item.partition(":")
                key = key.strip()
                value = remainder.strip()
                if value == "":
                    node: Any = {}
                    parent.append({key: node})
                    stack.append((indent + 2, node))
                else:
                    parent.append({key: _parse_scalar(value)})
            else:
                parent.append(_parse_scalar(item))

            last_key = None
            continue

        if isinstance(parent, list):
            if not parent or not isinstance(parent[-1], dict):
                raise ValueError("Invalid YAML structure under list")
            parent = parent[-1]
            stack.append((indent, parent))

        if ":" not in stripped:
            continue

        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()

        if value == "":
            node: Any = {}
            parent[key] = node
            stack.append((indent, node))
        else:
            parent[key] = _parse_scalar(value)

        last_key = key

    return result


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


def project_root() -> Path:
    return PROJECT_ROOT


def resolve_project_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _load_yaml_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing configuration file: {path}")
    content = path.read_text()
    if _HAS_YAML:
        return yaml.safe_load(content) or {}
    return _load_simple_yaml(content)

def load_yaml_file(path: Path) -> Dict[str, Any]:
    return _load_yaml_file(path)

@dataclass
class AppConfig:
    name: str
    timezone: str
    default_run_mode: str
    weekly_package_day: str
    weekly_package_window_start: str
    weekly_package_window_end: str

@dataclass
class StorageConfig:
    sqlite_path: str
    exports_dir: str
    review_packets_dir: str
    logs_dir: str

@dataclass
class ReviewConfig:
    approval_method: str
    notification_channel: str
    approval_host: str
    token_expiration_hours: int

@dataclass
class PublishingConfig:
    target: str
    default_mode: str
    linkedin_api_enabled: bool
    require_approval_record: bool
    require_content_hash_match: bool
    text_only_first: bool
    media_publishing_enabled: bool

@dataclass
class LoggingConfig:
    level: str
    format: str

@dataclass
class Config:
    app: AppConfig
    storage: StorageConfig
    review: ReviewConfig
    publishing: PublishingConfig
    logging: LoggingConfig

def validate_config(config: Config) -> None:
    """Validate configuration values"""
    # Validate run mode
    valid_modes = ["hard_zero", "free_tier_plus_guardrails", "future_paid_mode"]
    if config.app.default_run_mode not in valid_modes:
        raise ValueError(f"Invalid run mode: {config.app.default_run_mode}. Must be one of {valid_modes}")
    
    # Validate timezone (basic check)
    if not config.app.timezone:
        raise ValueError("Timezone cannot be empty")
    
    # Validate weekly day
    valid_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    if config.app.weekly_package_day.lower() not in valid_days:
        raise ValueError(f"Invalid weekly package day: {config.app.weekly_package_day}. Must be one of {valid_days}")
    
    # Validate time format
    import re
    time_pattern = re.compile(r"^\d{2}:\d{2}$")
    if not time_pattern.match(config.app.weekly_package_window_start):
        raise ValueError(f"Invalid time format for weekly_package_window_start: {config.app.weekly_package_window_start}")
    if not time_pattern.match(config.app.weekly_package_window_end):
        raise ValueError(f"Invalid time format for weekly_package_window_end: {config.app.weekly_package_window_end}")
    
    # Validate logging level
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if config.logging.level not in valid_levels:
        raise ValueError(f"Invalid logging level: {config.logging.level}. Must be one of {valid_levels}")
    
    # Validate paths exist or can be created
    storage_paths = [
        config.storage.sqlite_path,
        config.storage.exports_dir,
        config.storage.review_packets_dir,
        config.storage.logs_dir
    ]
    for path_str in storage_paths:
        path = resolve_project_path(path_str)
        if path.suffix == '.db':
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            path.mkdir(parents=True, exist_ok=True)

def load_config() -> Config:
    """Load configuration from YAML files"""
    _load_env_file(PROJECT_ROOT / ".env")
    config_path = CONFIG_DIR

    app_data = _load_yaml_file(config_path / "app.yaml")
    _ = _load_yaml_file(config_path / "cost_guard.yaml")
    publishing_file = config_path / "publishing.yaml"
    if publishing_file.exists():
        publishing_data = _load_yaml_file(publishing_file)
        if "publishing" in publishing_data:
            app_data["publishing"] = {
                **app_data.get("publishing", {}),
                **publishing_data["publishing"],
            }

    if os.environ.get("RUN_MODE"):
        app_data.setdefault("app", {})["default_run_mode"] = os.environ["RUN_MODE"]
    if os.environ.get("DATABASE_PATH"):
        app_data.setdefault("storage", {})["sqlite_path"] = os.environ["DATABASE_PATH"]

    publishing_allowed_keys = {field.name for field in fields(PublishingConfig)}
    publishing_data = {
        key: value
        for key, value in app_data["publishing"].items()
        if key in publishing_allowed_keys
    }

    config = Config(
        app=AppConfig(**app_data["app"]),
        storage=StorageConfig(**app_data["storage"]),
        review=ReviewConfig(**app_data["review"]),
        publishing=PublishingConfig(**publishing_data),
        logging=LoggingConfig(**app_data["logging"])
    )
    
    # Validate config
    validate_config(config)
    
    return config
