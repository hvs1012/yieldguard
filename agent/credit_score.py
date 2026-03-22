"""
YieldGuard Credit Score Engine
--------------------------------
Computes an agent reputation score (0-850) from action history.

This implements the hackathon nice-to-have:
  "Use on-chain history for agent credit scores"

The score tracks the agent's own behavior reliability:
  - Successful supplies and repays build score (positive economic actions)
  - Liquidation alerts and cancellations reduce score (risk events)
  - Score adjusts the agent's own deployment behavior (genuine autonomy)

Score bands (mirrors FICO credit scoring):
  750-850  EXCELLENT  — increase max deployable by 20%
  600-749  GOOD       — normal operation
  400-599  FAIR       — reduce deployable by 20%, increase reserve buffer
  200-399  POOR       — repay-only mode, no new supplies
  0-199    CRITICAL   — hold all actions, alert user

The agent reads its own audit log, scores itself, and changes its behavior.
That is autonomy: the agent's past decisions constrain its future decisions.
"""

import json
import os


# ── Score weights ──────────────────────────────────────────────────────────────
WEIGHTS = {
    'supply':    +40,   # successful capital deployment
    'repay':     +30,   # successful debt reduction
    'withdraw':  +20,   # successful capital recovery
    'hold':      +2,    # healthy monitoring (small positive)
    'alert':     -80,   # liquidation risk detected (serious negative)
    'blocked':   -10,   # policy violation caught (minor negative — policy worked)
    'cancelled': -20,   # user cancelled proposed action
    'failed':    -50,   # transaction failed on-chain
}

STARTING_SCORE = 500
MAX_SCORE      = 850
MIN_SCORE      = 0

# ── Risk bands ────────────────────────────────────────────────────────────────
BANDS = [
    (750, 850, 'EXCELLENT', '#22c55e'),
    (600, 749, 'GOOD',      '#38bdf8'),
    (400, 599, 'FAIR',      '#f59e0b'),
    (200, 399, 'POOR',      '#ef4444'),
    (0,   199, 'CRITICAL',  '#dc2626'),
]


def compute_score(actions_path: str = 'actions.json') -> dict:
    """
    Reads the agent's action history and computes a credit score.

    Returns a dict with:
      score       int        0-850
      band        str        EXCELLENT / GOOD / FAIR / POOR / CRITICAL
      color       str        hex color for dashboard display
      trend       str        IMPROVING / STABLE / DECLINING
      breakdown   dict       count of each action type
      adjustments dict       how the score modifies agent behavior
      history     list       last 10 scored events
    """
    try:
        if not os.path.exists(actions_path):
            return _default_score()

        with open(actions_path) as f:
            actions = json.load(f)

        if not actions:
            return _default_score()

    except (json.JSONDecodeError, IOError):
        return _default_score()

    # Count actions
    breakdown = {}
    score     = STARTING_SCORE
    history   = []

    for entry in actions:
        action = entry.get('action', 'hold')
        weight = WEIGHTS.get(action, 0)
        score  = max(MIN_SCORE, min(MAX_SCORE, score + weight))
        breakdown[action] = breakdown.get(action, 0) + 1

        if weight != 0:
            history.append({
                'action':    action,
                'weight':    weight,
                'score':     score,
                'timestamp': entry.get('timestamp', '')[:19]
            })

    # Trend: compare last 5 vs previous 5 scored events
    scored = [h for h in history if h['weight'] != 0]
    if len(scored) >= 10:
        recent   = sum(h['weight'] for h in scored[-5:])
        previous = sum(h['weight'] for h in scored[-10:-5])
        trend = 'IMPROVING' if recent > previous else ('DECLINING' if recent < previous else 'STABLE')
    elif len(scored) >= 2:
        trend = 'IMPROVING' if scored[-1]['weight'] > 0 else 'STABLE'
    else:
        trend = 'STABLE'

    # Get band
    band, color = _get_band(score)

    # Compute behavioral adjustments based on score
    adjustments = _compute_adjustments(score, band)

    return {
        'score':       score,
        'band':        band,
        'color':       color,
        'trend':       trend,
        'breakdown':   breakdown,
        'adjustments': adjustments,
        'history':     history[-10:],  # last 10 events
        'total_actions': len(actions)
    }


def _get_band(score: int) -> tuple:
    for lo, hi, band, color in BANDS:
        if lo <= score <= hi:
            return band, color
    return 'GOOD', '#38bdf8'


def _compute_adjustments(score: int, band: str) -> dict:
    """
    The core autonomy feature: score changes agent behavior.

    These multipliers are applied to policy values in agent.py.
    A lower-scoring agent is more conservative automatically.
    """
    if band == 'EXCELLENT':
        return {
            'deployable_multiplier': 1.20,   # deploy 20% more
            'reserve_multiplier':    0.90,   # slightly lower reserve needed
            'mode':                  'ENHANCED',
            'description':           'Excellent track record — increased deployment capacity'
        }
    elif band == 'GOOD':
        return {
            'deployable_multiplier': 1.00,   # normal
            'reserve_multiplier':    1.00,   # normal
            'mode':                  'NORMAL',
            'description':           'Good track record — standard operation'
        }
    elif band == 'FAIR':
        return {
            'deployable_multiplier': 0.80,   # deploy 20% less
            'reserve_multiplier':    1.20,   # 20% higher reserve required
            'mode':                  'CAUTIOUS',
            'description':           'Fair track record — reduced deployment, higher reserve'
        }
    elif band == 'POOR':
        return {
            'deployable_multiplier': 0.00,   # no new supplies
            'reserve_multiplier':    1.50,
            'mode':                  'REPAY_ONLY',
            'description':           'Poor track record — repay-only mode active'
        }
    else:  # CRITICAL
        return {
            'deployable_multiplier': 0.00,
            'reserve_multiplier':    2.00,
            'mode':                  'HOLD',
            'description':           'Critical score — all actions paused, manual review needed'
        }


def apply_to_policy(policy: dict, credit: dict) -> dict:
    """
    Returns a modified policy dict with credit score adjustments applied.
    Original policy is not mutated.
    """
    adj = credit['adjustments']
    p   = policy.copy()

    mult = adj['deployable_multiplier']
    if mult == 0.0:
        # repay-only or hold mode — set min_idle so high that supply never triggers
        p['min_idle_usdt'] = 999999
    else:
        # Adjust reserve buffer
        p['reserve_buffer'] = policy['reserve_buffer'] * adj['reserve_multiplier']

    return p


def _default_score() -> dict:
    """Returns starting score when no history exists."""
    band, color = _get_band(STARTING_SCORE)
    return {
        'score':       STARTING_SCORE,
        'band':        band,
        'color':       color,
        'trend':       'STABLE',
        'breakdown':   {},
        'adjustments': _compute_adjustments(STARTING_SCORE, band),
        'history':     [],
        'total_actions': 0
    }
