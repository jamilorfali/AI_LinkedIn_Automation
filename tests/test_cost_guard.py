from ai_linkedin_automation.cost_guard import check_cost_allowed


def test_cost_guard_blocks_paid_api_in_hard_zero():
    config = {"run_mode": "hard_zero", "monthly_spend_cap_usd": 0}
    decision = check_cost_allowed("openai_api", "draft", cost_config=config)
    assert decision.allowed is False
    assert "Hard Zero" in decision.reason


def test_cost_guard_blocks_nonzero_cost_in_hard_zero():
    config = {"run_mode": "hard_zero", "monthly_spend_cap_usd": 0}
    decision = check_cost_allowed("public_web_fetch", "fetch", 0.01, cost_config=config)
    assert decision.allowed is False
    assert "Non-zero" in decision.reason


def test_cost_guard_allows_local_rss_in_hard_zero():
    config = {"run_mode": "hard_zero", "monthly_spend_cap_usd": 0}
    decision = check_cost_allowed("public_rss", "fetch", cost_config=config)
    assert decision.allowed is True


def test_cost_guard_allows_manual_links_in_hard_zero():
    config = {"run_mode": "hard_zero", "monthly_spend_cap_usd": 0}
    decision = check_cost_allowed("manual_link", "read_inbox", cost_config=config)
    assert decision.allowed is True
