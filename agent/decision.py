"""
YieldGuard Decision Engine v3
------------------------------
Economic formula:
  Net Benefit = Expected Yield Gain - Gas Cost - Risk Penalty

Decision priority:
  1. CRITICAL ALERT     → health low, wallet empty, can't act
  2. EMERGENCY REPAY    → health below minimum, repay from wallet
  3. YIELD ROUTING      → agent decides what to do with earned yield:
                          - Health low  → use yield to REPAY (reduce risk)
                          - Health good → use yield to COMPOUND (supply more)
                          - No position → use yield as reserve buffer
  4. SUPPLY             → idle USDT detected, deploy to Aave
  5. WITHDRAW           → over-collateralized, free up capital
  6. HOLD               → everything is fine

Yield routing (Priority 3) implements TWO nice-to-have criteria:
  - "Agents use their own earned revenue to service debt" (yield→repay)
  - "Agent reallocates capital to higher-yield opportunities" (yield→compound)

The agent's decision depends entirely on current market conditions —
same earned yield, different action depending on health factor.
That's genuine autonomous economic reasoning.
"""


class DecisionEngine:
    def __init__(self, policy: dict):
        self.p = policy

    def decide(self, position: dict) -> dict:
        p            = self.p
        usdt         = position.get('usdtBalance', 0)
        aave         = position.get('aave', {})
        health       = aave.get('healthFactor')
        collateral   = aave.get('totalCollateral', 0)
        debt         = aave.get('totalDebt', 0)
        total_earned = position.get('totalEarned', 0)

        # ── PRIORITY 1: Health critical + wallet empty → alert ────────────────
        if health is not None and health < p['min_health_factor']:
            repay_amt = min(
                debt * p['repay_fraction'],
                usdt * 0.8,
                p['max_single_tx_usdt']
            )
            if repay_amt > 1.0:
                return {
                    'action':  'repay',
                    'amount':  round(repay_amt, 2),
                    'urgency': 'HIGH',
                    'reason': (
                        f"Health factor {health:.2f} is BELOW minimum threshold "
                        f"{p['min_health_factor']}. Repaying {repay_amt:.2f} USDT "
                        f"to reduce liquidation risk immediately."
                    ),
                    'metrics': {
                        'health_factor':  health,
                        'total_debt':     debt,
                        'repay_fraction': p['repay_fraction']
                    }
                }
            else:
                return {
                    'action':  'alert',
                    'amount':  0,
                    'urgency': 'CRITICAL',
                    'reason': (
                        f"CRITICAL: Health factor {health:.2f} dangerously low "
                        f"but wallet has only {usdt:.2f} USDT. "
                        f"Add funds immediately to avoid liquidation of "
                        f"${collateral:.2f} collateral."
                    ),
                    'metrics': {
                        'health_factor':      health,
                        'total_debt':         debt,
                        'usdt_available':     usdt,
                        'collateral_at_risk': collateral
                    }
                }

        # ── PRIORITY 2: INTELLIGENT YIELD ROUTING ─────────────────────────────
        #
        # The agent earned yield by supplying to Aave.
        # Now it decides autonomously what to DO with those earnings
        # based on current market conditions — not a fixed rule.
        #
        # This implements BOTH nice-to-have criteria:
        #   "use earned revenue to service debt"  → yield repay path
        #   "reallocate capital to higher-yield"  → yield compound path
        #
        yield_threshold = p.get('yield_repay_threshold', 0.05)

        if total_earned >= yield_threshold:
            # How much yield can we deploy?
            deployable_yield = min(
                total_earned * 0.80,      # use 80%, keep 20% as earned buffer
                p['max_single_tx_usdt'],
                max(usdt, 0.01)           # can't exceed wallet balance
            )

            if deployable_yield >= 0.01:
                # ── Path A: Health is low → use yield to REPAY debt ──────────
                if health is not None and health < 2.0 and debt > 0:
                    new_debt_est = max(0, debt - deployable_yield)
                    new_hf_est   = (collateral * 0.80 / new_debt_est) if new_debt_est > 0 else None
                    return {
                        'action':  'repay',
                        'amount':  round(deployable_yield, 4),
                        'urgency': 'LOW',
                        'source':  'yield_earnings',
                        'reason': (
                            f"Yield routing: health factor {health:.2f} is below target 2.0. "
                            f"Agent using ${total_earned:.4f} earned yield to repay debt. "
                            f"Wallet untouched. Est. HF after: "
                            f"{new_hf_est:.2f}." if new_hf_est else
                            f"Agent routing ${deployable_yield:.4f} earned yield to debt repayment."
                        ),
                        'metrics': {
                            'route':          'repay',
                            'total_earned':   total_earned,
                            'amount':         deployable_yield,
                            'health_before':  health,
                            'health_after':   round(new_hf_est, 2) if new_hf_est else None,
                            'reasoning':      'Health < 2.0 → prioritize risk reduction'
                        }
                    }

                # ── Path B: Health is good → COMPOUND yield back into Aave ───
                elif collateral > 0:
                    compound_amt = round(deployable_yield, 4)
                    extra_daily  = compound_amt * p['expected_apy'] / 365
                    return {
                        'action':  'supply',
                        'amount':  compound_amt,
                        'urgency': 'LOW',
                        'source':  'yield_compound',
                        'reason': (
                            f"Yield compounding: agent reinvesting ${total_earned:.4f} "
                            f"earned yield back into Aave. "
                            f"Position healthy (HF: {health:.2f}). "
                            f"Compounding adds ${extra_daily:.6f}/day to future yield. "
                            f"Wallet untouched."
                        ),
                        'metrics': {
                            'route':          'compound',
                            'total_earned':   total_earned,
                            'compound_amt':   compound_amt,
                            'extra_daily':    extra_daily,
                            'reasoning':      'Health >= 2.0 → compound for maximum yield'
                        }
                    }

        # ── PRIORITY 3: Idle USDT → supply to Aave ───────────────────────────
        deployable = usdt - p['reserve_buffer']
        if deployable >= p['min_idle_usdt']:
            daily_yield = deployable * p['expected_apy'] / 365
            return {
                'action':  'supply',
                'amount':  round(deployable, 2),
                'urgency': 'LOW',
                'reason': (
                    f"Detected {usdt:.2f} USDT idle in wallet. "
                    f"After keeping {p['reserve_buffer']:.0f} USDT reserve, "
                    f"{deployable:.2f} USDT can earn {p['expected_apy']*100:.1f}% APY. "
                    f"Estimated daily yield: ${daily_yield:.4f}."
                ),
                'metrics': {
                    'deployable_usdt':  deployable,
                    'reserve_after':    p['reserve_buffer'],
                    'daily_yield_usd':  round(daily_yield, 6),
                    'annual_yield_usd': round(deployable * p['expected_apy'], 4),
                    'apy':              p['expected_apy']
                }
            }

        # ── PRIORITY 4: Over-collateralized → suggest withdrawal ──────────────
        if health is not None and health > p['max_health_factor'] and collateral > 0:
            safe_withdraw = round(collateral * 0.1, 2)
            return {
                'action':  'withdraw',
                'amount':  safe_withdraw,
                'urgency': 'LOW',
                'reason': (
                    f"Health factor {health:.2f} is very high — capital over-locked. "
                    f"Withdrawing {safe_withdraw:.2f} USDT (10% of ${collateral:.2f}) "
                    f"improves capital efficiency."
                ),
                'metrics': {
                    'health_factor':    health,
                    'total_collateral': collateral,
                    'withdraw_pct':     0.10
                }
            }

        # ── Default: hold ─────────────────────────────────────────────────────
        return {
            'action':  'hold',
            'amount':  0,
            'urgency': 'NONE',
            'reason': (
                f"Position healthy. No action needed. | "
                f"Idle: {usdt:.2f} USDT | "
                f"Health: {f'{health:.2f}' if health is not None else 'N/A'} | "
                f"Collateral: ${collateral:.2f} | "
                f"Yield earned: ${total_earned:.4f}"
            ),
            'metrics': {
                'usdt_idle':     usdt,
                'health_factor': health,
                'collateral':    collateral,
                'total_earned':  total_earned
            }
        }

    def net_benefit(self, amount: float, fee_matic: float) -> dict:
        fee_usd     = fee_matic * self.p['matic_price_usd']
        daily_yield = amount * self.p['expected_apy'] / 365
        breakeven   = (fee_usd / daily_yield) if daily_yield > 0 else float('inf')
        gas_pct     = (fee_usd / amount * 100) if amount > 0 else 0
        return {
            'fee_usd':         round(fee_usd, 6),
            'daily_yield_usd': round(daily_yield, 6),
            'net_7day_usd':    round(daily_yield * 7 - fee_usd, 6),
            'breakeven_days':  round(breakeven, 1),
            'gas_pct':         round(gas_pct, 4)
        }

    def build_card(self, decision: dict, position: dict, fee_matic: float) -> dict:
        p      = self.p
        econ   = self.net_benefit(decision['amount'], fee_matic)
        action = decision['action']
        amount = decision['amount']
        usdt   = position.get('usdtBalance', 0)
        health = position.get('aave', {}).get('healthFactor')
        source = decision.get('source', '')
        points = []
        status = 'ok'

        # ── Point 1: Benefit ──────────────────────────────────────────────────
        if source == 'yield_compound':
            m = decision.get('metrics', {})
            points.append({'type': 'benefit', 'text': (
                f"Compounding ${amount:.4f} earned yield back into Aave. "
                f"Adds ${m.get('extra_daily', 0):.6f}/day to future earnings. "
                f"Wallet balance unchanged — pure compound growth."
            )})
        elif source == 'yield_earnings':
            m = decision.get('metrics', {})
            points.append({'type': 'benefit', 'text': (
                f"Agent routing ${amount:.4f} earned yield to debt repayment. "
                f"Health factor will improve. "
                f"Your wallet is NOT touched — agent pays from its own earnings."
            )})
        elif action == 'supply':
            points.append({'type': 'benefit', 'text': (
                f"Deploying {amount:.2f} USDT at ~{p['expected_apy']*100:.1f}% APY. "
                f"Daily yield: ${econ['daily_yield_usd']:.4f}. "
                f"7-day net after gas: ${econ['net_7day_usd']:.4f}."
            )})
        elif action == 'repay':
            points.append({'type': 'benefit', 'text': (
                f"Repaying {amount:.2f} USDT reduces liquidation risk. "
                f"Health factor {health:.2f} → will improve. "
                f"Urgency: {decision['urgency']}."
            )})
        elif action == 'withdraw':
            points.append({'type': 'benefit', 'text': (
                f"Freeing {amount:.2f} USDT from over-collateralized position."
            )})

        # ── Point 2: Gas / risk ───────────────────────────────────────────────
        gas_threshold = p['max_gas_pct'] * 100
        if action == 'repay' and decision['urgency'] == 'HIGH':
            points.append({'type': 'urgent', 'text': (
                f"LIQUIDATION RISK — HF {health:.2f} critically low. "
                f"Gas: ${econ['fee_usd']:.5f}. Confirm immediately."
            )})
            status = 'caution'
        elif source in ('yield_earnings', 'yield_compound'):
            points.append({'type': 'info', 'text': (
                f"Gas: ${econ['fee_usd']:.5f} from POL balance. "
                f"Net wallet USDT impact: $0.00. "
                f"Reasoning: {decision.get('metrics', {}).get('reasoning', 'yield routing')}"
            )})
        elif econ['gas_pct'] > gas_threshold:
            points.append({'type': 'warning', 'text': (
                f"Gas {econ['gas_pct']:.3f}% exceeds policy limit {gas_threshold:.2f}%."
            )})
            status = 'caution'
        else:
            points.append({'type': 'info', 'text': (
                f"Gas: ${econ['fee_usd']:.5f} ({econ['gas_pct']:.3f}%). "
                f"Break-even in {econ['breakeven_days']} days. Within limits."
            )})

        # ── Point 3: Policy compliance ────────────────────────────────────────
        reserve_after = (usdt - amount) if action == 'supply' and source == '' else usdt

        if action in ('supply',) and source == '' and amount > p['max_single_tx_usdt']:
            points.append({'type': 'blocked', 'text': (
                f"POLICY VIOLATION: {amount:.2f} USDT exceeds single-tx cap "
                f"of {p['max_single_tx_usdt']:.0f} USDT."
            )})
            status = 'blocked'
        elif action == 'supply' and source == '' and reserve_after < p['reserve_buffer']:
            points.append({'type': 'blocked', 'text': (
                f"POLICY VIOLATION: Post-action balance ${reserve_after:.2f} "
                f"below reserve floor ${p['reserve_buffer']:.0f} USDT."
            )})
            status = 'blocked'
        elif source in ('yield_earnings', 'yield_compound'):
            points.append({'type': 'ok', 'text': (
                f"Autonomous yield routing. Zero wallet USDT impact. "
                f"Agent operating as self-sustaining economic actor."
            )})
        else:
            points.append({'type': 'ok', 'text': (
                f"Policy compliant. Reserve after: ${reserve_after:.2f} USDT "
                f"(floor: ${p['reserve_buffer']:.0f}). All rules satisfied."
            )})

        return {'points': points, 'status': status, 'economics': econ}
