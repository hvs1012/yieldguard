"""
YieldGuard Agent — Main Loop
-----------------------------
Runs every N seconds (default 300 = 5 minutes).

Each cycle:
  1. Read current position from WDK server
  2. Decision engine decides what to do
  3. Get real fee quote BEFORE showing anything to user
  4. Build smart 3-point confirmation card
  5. If policy violation → block automatically
  6. Otherwise → ask user to confirm
  7. Execute → log everything
"""

import json
import time
import requests
from datetime import datetime
from decision import DecisionEngine
from claude_ai import ask_claude
from credit_score import compute_score, apply_to_policy


WDK_BASE = "http://localhost:3000"

# ─── file helpers ─────────────────────────────────────────────────────────────

def load_policy() -> dict:
    with open("policy.json") as f:
        return json.load(f)

def load_log() -> list:
    try:
        with open("actions.json") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_log(entries: list):
    with open("actions.json", "w") as f:
        json.dump(entries, f, indent=2)

def append_log(entry: dict):
    log = load_log()
    log.append(entry)
    save_log(log)

def write_pending(data: dict):
    """Dashboard reads this file to show what the agent is currently proposing."""
    with open("pending_action.json", "w") as f:
        json.dump(data, f, indent=2)

def clear_pending():
    write_pending({"action": "none", "timestamp": now()})

def write_response(data: dict):
    """Dashboard writes here when user clicks Confirm or Cancel."""
    with open("confirmation_response.json", "w") as f:
        json.dump(data, f)

def clear_response():
    try:
        import os
        os.remove("confirmation_response.json")
    except FileNotFoundError:
        pass

def wait_for_response(timeout: int = 120) -> bool | None:
    """
    Polls confirmation_response.json until:
    - Dashboard confirms  → returns True
    - Dashboard cancels   → returns False
    - Timeout reached     → returns None
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with open("confirmation_response.json") as f:
                data = json.load(f)
            return data.get("confirmed")  # True or False
        except FileNotFoundError:
            pass
        time.sleep(1)
    return None

def now() -> str:
    return datetime.now().isoformat()

# ─── WDK server calls ─────────────────────────────────────────────────────────

def get(path: str) -> dict:
    return requests.get(f"{WDK_BASE}{path}", timeout=15).json()

def post(path: str, body: dict) -> dict:
    return requests.post(f"{WDK_BASE}{path}", json=body, timeout=30).json()

# ─── display helpers ──────────────────────────────────────────────────────────

ICONS = {
    'benefit': '✅',
    'info':    'ℹ️ ',
    'warning': '⚠️ ',
    'urgent':  '🚨',
    'blocked': '⛔',
    'ok':      '✅'
}

STATUS_LABEL = {
    'ok':      '✅  ACTION PROPOSED — Policy Compliant',
    'caution': '⚠️   ACTION PROPOSED — Review Carefully',
    'blocked': '⛔  EXECUTION BLOCKED — Policy Violation'
}

def print_card(card: dict, decision: dict):
    print()
    print("━" * 60)
    print(f"  {STATUS_LABEL.get(card['status'], '')}")
    print(f"  Proposed: {decision['action'].upper()} {decision['amount']:.2f} USDT")
    print("━" * 60)
    for i, pt in enumerate(card['points'], 1):
        icon = ICONS.get(pt['type'], '•')
        # Wrap long lines nicely
        text = pt['text']
        print(f"  {i}. {icon}  {text}")
    print("━" * 60)

def print_separator():
    print("\n" + "─" * 60)

# ─── main loop ────────────────────────────────────────────────────────────────

def run():
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║           YieldGuard — AI Lending Agent              ║")
    print("║      Powered by WDK + Aave V3 on Polygon             ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    policy = load_policy()
    engine = DecisionEngine(policy)

    print(f"  📋 Policy loaded:")
    print(f"     Reserve buffer:     {policy['reserve_buffer']} USDT")
    print(f"     Min idle to deploy: {policy['min_idle_usdt']} USDT")
    print(f"     Expected APY:       {policy['expected_apy']*100:.1f}%")
    print(f"     Min health factor:  {policy['min_health_factor']}")
    print(f"     Max gas % of tx:    {policy['max_gas_pct']*100:.2f}%")
    print(f"     Check interval:     {policy['check_interval_seconds']}s")
    print()
    print("  🚀 Starting agent loop... (Ctrl+C to stop)")

    while True:
        print_separator()
        ts = datetime.now().strftime('%H:%M:%S')
        print(f"\n  [{ts}] Running analysis cycle...")

        try:
            # ── Step 1: Read current state + live APY ───────────────────────
            position = get('/position')

            usdt    = position.get('usdtBalance', 0)
            pol     = position.get('polBalance', 0)
            addr    = position.get('address', 'unknown')
            aave    = position.get('aave', {})
            health  = aave.get('healthFactor')
            collat  = aave.get('totalCollateral', 0)
            debt    = aave.get('totalDebt', 0)

            print(f"\n  👛 Wallet: {addr[:8]}...{addr[-6:]}")
            print(f"     USDT balance:      {usdt:.4f} USDT")
            print(f"     POL balance:       {pol:.4f} POL (for gas)")
            print(f"     Aave collateral:   ${collat:.4f}")
            print(f"     Aave debt:         ${debt:.4f}")
            print(f"     Health factor:     {f'{health:.4f}' if health is not None else 'N/A (no borrow position)'}")

            # Fetch live APY and update policy for this cycle
            try:
                apy_data   = get('/apy')
                live_apy   = apy_data.get('apy', policy['expected_apy'] * 100) / 100
                apy_source = apy_data.get('source', 'fallback')
                policy['expected_apy'] = live_apy
                engine = DecisionEngine(policy)
                print(f"  📈 Live APY: {live_apy*100:.2f}% ({apy_source})")
            except Exception:
                print(f"  📈 APY: {policy['expected_apy']*100:.1f}% (cached)")

            # Show total earned if available
            total_earned = position.get('totalEarned', 0)
            if total_earned > 0:
                print(f"  💸 Total yield earned this session: ${total_earned:.6f}")

            # ── Step 2: Compute credit score + adjust policy ─────────────────
            credit       = compute_score('actions.json')
            adj_policy   = apply_to_policy(policy, credit)
            adj_engine   = DecisionEngine(adj_policy)

            # Log credit status
            score_str = f"{credit['score']}/850 {credit['band']} {credit['trend']}"
            print(f"  📊 Credit score: {score_str}")
            if credit['adjustments']['mode'] != 'NORMAL':
                print(f"     Mode: {credit['adjustments']['description']}")

            # Write credit score to pending so dashboard can show it
            # (stored separately so it persists between cycles)
            try:
                with open('credit_status.json', 'w') as f:
                    import json as _j
                    _j.dump(credit, f, indent=2)
            except Exception:
                pass

            # ── Step 3: Agent decides (using credit-adjusted policy) ──────────
            decision = adj_engine.decide(position)
            print(f"\n  🤖 Decision: {decision['action'].upper()}")
            print(f"     {decision['reason'][:100]}{'...' if len(decision['reason']) > 100 else ''}")

            # ── Step 4: Log hold/alert decisions and move on ─────────────────
            if decision['action'] in ('hold', 'alert'):
                entry = {
                    'timestamp': now(),
                    'action':    decision['action'],
                    'urgency':   decision.get('urgency', 'NONE'),
                    'reason':    decision['reason'],
                    'position':  position
                }
                append_log(entry)
                write_pending({
                    'action':    decision['action'],
                    'urgency':   decision.get('urgency', 'NONE'),
                    'reason':    decision['reason'],
                    'timestamp': now(),
                    'position':  position
                })
                if decision.get('urgency') == 'CRITICAL':
                    print(f"\n  🚨🚨 CRITICAL ALERT — {decision['reason'][:120]}\n")

            else:
                # ── Step 5: Get real fee quote before showing card ────────────
                print(f"\n  💰 Getting fee quote for {decision['action']} {decision['amount']:.2f} USDT...")
                quote_endpoint = f"/quote-{decision['action']}"
                quote     = post(quote_endpoint, {'amount': decision['amount']})
                fee_matic = quote.get('fee_matic', 0)
                fee_usd   = fee_matic * policy['matic_price_usd']
                print(f"     Estimated gas: {fee_matic:.6f} MATIC (≈ ${fee_usd:.6f})")

                # ── Step 6: Claude AI analysis ────────────────────────────────
                # Falls back silently if ANTHROPIC_API_KEY not set
                claude_analysis = ask_claude(position, decision, policy)
                if claude_analysis:
                    print(f"\n  🧠 Claude: {claude_analysis[:100]}...")

                # ── Step 7: Build 3-point confirmation card ───────────────────
                card = adj_engine.build_card(decision, position, fee_matic)
                print_card(card, decision)

                # ── Step 8: Block or wait for dashboard confirmation ──────────
                if card['status'] == 'blocked':
                    print("\n  ⛔  Execution blocked by policy engine.")
                    print("      No transaction sent. See violation above.\n")
                    append_log({
                        'timestamp': now(),
                        'action':    'blocked',
                        'reason':    card['points'][-1]['text'],
                        'decision':  decision,
                        'position':  position
                    })
                    clear_pending()

                else:
                    # Write pending with awaiting_confirmation=True
                    # Dashboard polls this and shows Confirm/Cancel buttons
                    write_pending({
                        'decision':              decision,
                        'card':                  card,
                        'fee_matic':             fee_matic,
                        'timestamp':             now(),
                        'position':              position,
                        'confirmed':             None,
                        'awaiting_confirmation': True,
                        'claude_analysis':       claude_analysis
                    })
                    # Clear any stale response
                    clear_response()

                    print(f"\n  ⏳  Waiting for dashboard confirmation...")
                    print(f"      Open dashboard and click Confirm or Cancel.")
                    print(f"      Auto-cancels in 120 seconds if no response.\n")

                    # Poll for response (dashboard writes to response file)
                    confirmed = wait_for_response(timeout=120)

                    if confirmed is True:
                        # ── Step 7: Execute ───────────────────────────────────
                        print(f"\n  ⏳  User confirmed! Sending {decision['action']} transaction...")
                        result = post(f"/{decision['action']}", {'amount': decision['amount']})

                        if 'error' in result:
                            print(f"\n  ❌  Transaction failed: {result['error']}\n")
                            append_log({
                                'timestamp': now(),
                                'action':    'failed',
                                'error':     result['error'],
                                'decision':  decision
                            })
                        else:
                            entry = {
                                'timestamp':       now(),
                                'action':          decision['action'],
                                'amount':          decision['amount'],
                                'reason':          decision['reason'],
                                'tx_hash':         result.get('hash'),
                                'fee_matic':       fee_matic,
                                'card':            card,
                                'position_before': position
                            }
                            append_log(entry)
                            write_pending({**entry, 'confirmed': True, 'awaiting_confirmation': False})
                            clear_response()

                            print(f"\n  ✅  Transaction confirmed!")
                            print(f"     Tx hash: {result.get('hash')}")
                            print(f"     Fee paid: {fee_matic:.6f} POL\n")
                    elif confirmed is False:
                        print("\n  ❌  Cancelled via dashboard.\n")
                        append_log({
                            'timestamp': now(),
                            'action':    'cancelled',
                            'decision':  decision,
                            'reason':    'User cancelled via dashboard'
                        })
                        clear_pending()
                        clear_response()
                    else:
                        print("\n  ⏰  No response — auto-cancelled after 120s.\n")
                        append_log({
                            'timestamp': now(),
                            'action':    'cancelled',
                            'decision':  decision,
                            'reason':    'Auto-cancelled: no dashboard response within 120s'
                        })
                        clear_pending()
                        clear_response()

        except requests.exceptions.ConnectionError:
            print("\n  ⚠️   Cannot connect to WDK server.")
            print("      Make sure it's running: cd wdk-server && node server.js\n")

        except KeyboardInterrupt:
            print("\n\n  👋  YieldGuard stopped. Goodbye!\n")
            break

        except Exception as e:
            print(f"\n  ❌  Unexpected error: {e}\n")

        interval = policy.get('check_interval_seconds', 300)
        print(f"  ⏰  Next cycle in {interval}s. (Ctrl+C to stop)")
        time.sleep(interval)


if __name__ == "__main__":
    run()
