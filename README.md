# YieldGuard — Autonomous USDT Lending Agent

> An AI agent that monitors Aave V3 positions, deploys idle USDT to maximize yield, protects against liquidation, and uses its own earned yield to autonomously service debt. Built on WDK. Designed for human-supervised autonomous execution - agent monitors and decides independently, human confirms write actions via dashboard for safety.

**Track:** Lending Bot · **Hackathon:** Tether Hackathon Galactica WDK Edition 1

---

## What it does

1. **Deploys idle USDT to Aave V3** — monitors wallet every 15 seconds, calculates net yield vs gas cost, executes only when profitable
2. **Protects against liquidation** — detects dangerous health factors instantly, proposes emergency repayment with full economic reasoning
3. **Autonomous yield routing** — Yield-aware debt service, earned yield is reinvested or used to repay debt based on current market conditions, zero wallet impact
4. **Agent credit scoring** — tracks own reliability (0–850 FICO-style), automatically adjusts deployment capacity based on past behavior
5. **Agent-to-agent lending** — lends idle capital to borrower agents, evaluates credit scores, auto-collects repayment when job completes

> The agent is autonomous. The human stays in control.

---

## Live Demo

Dashboard hosted on GitHub Pages — backend runs locally via ngrok tunnel.

**[View Dashboard →](https://hvs1012.github.io/yieldguard/)**

To connect the live backend:
```
https://hvs1012.github.io/yieldguard/?backend=https://barometric-knox-unbreaking.ngrok-free.dev
```

> If the backend appears offline, the ngrok session may have expired. Run locally following setup instructions below.

---

## Core Features

| Feature | Description |
|---------|-------------|
| Yield Deployment | Monitors idle USDT, calculates net benefit, supplies to Aave V3 |
| Liquidation Protection | Detects health factor drops, proposes emergency repayment |
| Intelligent Yield Routing | Routes earned yield to repay debt or compound — decided autonomously |
| Yield Compounding | Agent reinvests its own earnings back into Aave for compound growth |
| Agent Credit Score | 0–850 FICO-style score based on behavior, adjusts deployment limits |
| Agent-to-Agent Lending | Lends idle pool capital to borrower agents, auto-collects repayment |
| Policy Engine | Hard rules block bad decisions before execution — no overrides |
| Confirmation Gate | Every write action requires explicit dashboard approval |

---

## Yield Self-Service

```
Normal flow:    User wallet USDT → repay debt   (costs user money)

YieldGuard:     Aave collateral earns yield every block
                → yield tracked in totalEarned
                → when earned ≥ $0.05 threshold
                → agent repays debt from earned yield
                → user wallet: $0.00 impact
                → agent is economically self-sustaining
```

The agent earns money by supplying. Then uses that money to reduce its own debt. Zero human input. Zero wallet impact.

---

## Economic Formula

```
Net Benefit = Expected Yield Gain − Gas Cost

Deploy USDT only if:
  Net Benefit > 0
  Gas cost < max_gas_pct × amount
  Reserve buffer remains intact
  Amount < max_single_tx_usdt

Repay debt if:
  Health Factor < min_health_factor (1.5)

Self-service debt if:
  Earned yield ≥ yield_repay_threshold ($0.05)

Withdraw if:
  Health Factor > max_health_factor (3.5)
```

---

## Architecture

```
┌─────────────────────────────────────────────┐
│              Python Agent (brain)            │
│                                              │
│  agent.py        Main loop, 15s interval     │
│  decision.py     Economic decision engine    │
│  credit_score.py Behavior-based reputation   │
│  claude_ai.py    Claude Sonnet reasoning     │
│  policy.json     Configurable rules          │
│  actions.json    Immutable audit log         │
└──────────────────┬──────────────────────────┘
                   │ HTTP (localhost or ngrok)
┌──────────────────▼──────────────────────────┐
│         Node.js WDK Server (:3000)           │
│                                              │
│  GET  /position       wallet + Aave state   │
│  POST /supply         deposit to Aave       │
│  POST /repay          repay debt            │
│  POST /withdraw       withdraw collateral   │
│  GET  /apy            live APY (DefiLlama)  │
│  POST /confirm        dashboard approval    │
│  POST /agents/*       A2A lending endpoints │
│  AUTO tick            30s auto-simulation   │
└──────────────────┬──────────────────────────┘
                   │ WDK SDK
┌──────────────────▼──────────────────────────┐
│     Aave V3 on Polygon / Amoy Testnet        │
│     @tetherto/wdk-wallet-evm                 │
│     @tetherto/wdk-protocol-lending-aave-evm  │
└─────────────────────────────────────────────┘
```

---

## Setup

### Prerequisites
- Node.js 18+ · Python 3.9+ · (Optional) Anthropic API key

### 1. Install
```bash
cd wdk-server && npm install
cd ../agent && pip install -r requirements.txt
```

### 2. Configure
```bash
# wdk-server/.env
SIMULATE=true                     # false for live Polygon Amoy
SEED_PHRASE=your twelve words     # only needed when SIMULATE=false
RPC_URL=https://rpc-amoy.polygon.technology

# .env.agent (optional)
ANTHROPIC_API_KEY=sk-ant-...      # enables Claude AI reasoning
```

### 3. Run
```bash
# Terminal 1
cd wdk-server && node server.js

# Terminal 2
cd agent && python agent.py

# Dashboard: open dashboard/index.html in browser
```

### 4. Remote dashboard via ngrok
```bash
ngrok http 3000
# Copy the https URL, then open:
# https://hvs1012.github.io/yieldguard/?backend=https://barometric-knox-unbreaking.ngrok-free.dev
```

---

## Policy Configuration

| Field | Default | Effect |
|-------|---------|--------|
| `reserve_buffer` | 50 USDT | Never deploy below this |
| `min_idle_usdt` | 20 USDT | Minimum idle before deploying |
| `min_health_factor` | 1.5 | Repay debt if health drops below |
| `max_health_factor` | 3.5 | Withdraw if health rises above |
| `max_gas_pct` | 1% | Block if gas > 1% of amount |
| `max_single_tx_usdt` | 500 | Hard cap per transaction |
| `yield_repay_threshold` | $0.05 | Self-service yield trigger |
| `check_interval_seconds` | 15 | Agent polling frequency |

---

## Demo Scenarios

**Scenario 1 — Supply:** Reset → agent detects 500 USDT idle → proposes supply → confirm via dashboard → watch collateral grow

**Scenario 2 — Danger repay:** Set HF to 1.2 via dashboard button → agent detects on next cycle → 🚨 LIQUIDATION RISK card → confirm repay → HF improves

**Scenario 3 — Policy block:** Set `max_single_tx_usdt: 10` → reset → agent proposes 450 USDT → ⛔ BLOCKED automatically

**Scenario 4 — Yield self-service:** Let simulation run → wait for `totalEarned > $0.05` → agent autonomously routes yield to repay debt or compound

**Scenario 5 — Agent-to-agent lending:** Fund pool → Agent B requests loan → credit score evaluated → loan approved → auto-repays after 60s.

Note: A2A lending runs on simulation layer. Core supply/repay/withdraw use real WDK calls.

---
## Tech Stack


- **Wallet:** Tether WDK (`wdk-wallet-evm`, `wdk-protocol-lending-aave-evm`)
- **Protocol:** Aave V3 on Polygon
- **Agent:** Python 3 — decision engine, credit score, policy rules
- **Server:** Node.js + Express — WDK wrapper
- **Dashboard:** Vanilla HTML/JS — live updates every 5s
- **APY data:** DefiLlama API (live market rates)

---

## Prior Art & Inspiration

- [DeFi Saver](https://defisaver.com) — production health factor automation on Aave
- [Yearn Finance](https://yearn.finance) — automated yield optimization vaults
- [Instadapp](https://instadapp.io) — programmable DeFi accounts with automation
- [Autonomous Agents on Blockchains](https://arxiv.org/abs/2412.02882)
- [SoK: Security and Privacy of AI Agents for Blockchain](https://arxiv.org/abs/2406.12775)

---

## License

MIT