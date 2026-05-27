from pathlib import Path

from ai_linkedin_automation.config import project_root, resolve_project_path


ROOT = project_root()
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"


def repo_path(path: str) -> Path:
    return resolve_project_path(path)
