"""
YieldGuard Claude AI Reasoning Module
---------------------------------------
Adds Claude Sonnet analysis on top of the rule-based decision engine.

Architecture:
  Rule engine  → decides WHAT action to take (fast, deterministic, safe)
  Claude       → explains WHY it makes sense given market conditions

This combination is stronger than pure LLM decisions (unpredictable)
or pure rules (no nuance). Claude's output is shown on the dashboard
as "AI Market Analysis" alongside the 3-point policy card.

Falls back silently if ANTHROPIC_API_KEY is not set.
"""

import os
import requests


def ask_claude(position: dict, decision: dict, policy: dict) -> str:
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return ""

    try:
        aave   = position.get('aave', {})
        health = aave.get('healthFactor')
        collat = aave.get('totalCollateral', 0)
        debt   = aave.get('totalDebt', 0)
        usdt   = position.get('usdtBalance', 0)
        earned = position.get('totalEarned', 0)
        apy    = policy.get('expected_apy', 0.045) * 100
        action = decision['action']
        amount = decision.get('amount', 0)
        source = decision.get('source', '')

        hf_str     = f"{health:.2f}" if health else "N/A (no borrow position)"
        source_str = "Agent using its own earned yield — wallet not touched" if source == 'yield_earnings' else ""

        prompt = (
            "You are a DeFi risk analyst reviewing an Aave V3 lending position.\n\n"
            "Current state:\n"
            f"- Wallet USDT: ${usdt:.2f}\n"
            f"- Aave collateral: ${collat:.2f}\n"
            f"- Aave debt: ${debt:.2f}\n"
            f"- Health factor: {hf_str}\n"
            f"- Current APY: {apy:.1f}%\n"
            f"- Yield earned this session: ${earned:.4f}\n\n"
            f"Proposed action: {action.upper()} ${amount:.4f} USDT\n"
            f"{source_str}\n\n"
            "Write exactly 2 sentences:\n"
            "1. Assess whether this action is economically rational given the current state.\n"
            "2. Identify the single most important risk or opportunity the user should know.\n\n"
            "Be specific with numbers. No markdown. No bullet points. Plain text only."
        )

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json"
            },
            json={
                "model":      "claude-sonnet-4-5",
                "max_tokens": 150,
                "messages":   [{"role": "user", "content": prompt}]
            },
            timeout=10
        )

        if response.status_code == 200:
            return response.json()['content'][0]['text'].strip()
        return ""

    except Exception:
        return ""
