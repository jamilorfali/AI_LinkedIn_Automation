from datetime import datetime

from ai_linkedin_automation.config import project_root


def record_edit_learning(
    what_changed: str,
    pattern: str,
    log_path: str = "style/edit_learning_log.md",
) -> str:
    """Append a human edit learning note to the local style log."""
    path = project_root() / log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = "\n".join(
        [
            "",
            f"## {datetime.now().date().isoformat()}",
            "",
            "What changed:",
            f"- {what_changed.strip()}",
            "",
            "Pattern to remember:",
            f"- {pattern.strip()}",
            "",
        ]
    )
    with open(path, "a") as f:
        f.write(entry)
    return str(path)


def record_final_text_delta(original_text: str, final_text: str) -> str:
    """Record a concise style lesson when archived final text differs from draft text."""
    if original_text.strip() == final_text.strip():
        return ""
    return record_edit_learning(
        "Final archived post text differed from the approved draft.",
        "Review final manual edits and fold recurring changes into future draft style.",
    )
