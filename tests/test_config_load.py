from ai_linkedin_automation.config import load_config

def test_config_loads_defaults():
    config = load_config()
    assert config.app.name == "ai-linkedin-automation"
    assert config.app.default_run_mode == "hard_zero"
    assert config.app.timezone == "America/Chicago"
