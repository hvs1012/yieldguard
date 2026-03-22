# YieldGuard — Autonomous USDT Lending Agent

> An AI agent that monitors Aave V3 positions, deploys idle USDT to maximize yield,
> protects against liquidation, and — uniquely — uses its own earned yield to
> autonomously service debt. Built on WDK. Designed to run without human input.

**Track:** Lending Bot · **Hackathon:** Tether Hackathon Galactica WDK Edition 1

---

## What it does 

 YieldGuard is an economic agent:

1. **Deploys idle USDT to Aave V3** — monitors wallet every 15 seconds, calculates net yield vs gas cost, executes only when profitable
2. **Protects against liquidation** — detects dangerous health factors instantly, proposes emergency repayment with full economic reasoning
3. **Autonomous yield routing** — earned yield is reinvested or used to repay debt based on current market conditions, zero wallet impact
4. **Agent credit scoring** — tracks own reliability (0–850 FICO-style), automatically adjusts deployment capacity based on past behavior
5. **Agent-to-agent lending** — lends idle capital to borrower agents, evaluates credit scores, auto-collects repayment when job completes
The agent is autonomous. The human stays in control.

---

## Live Demo

Dashboard hosted on GitHub Pages — backend runs locally via ngrok tunnel.

**[View Dashboard →](https://hvs1012.github.io/yieldguard/)**

To connect your own backend:
```
https://hvs1012.github.io/yieldguard/?backend=https://barometric-knox-unbreaking.ngrok-free.dev

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
For every candidate action:

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
    Debt > 0

  Withdraw if:
    Health Factor > max_health_factor (3.5)
    Capital efficiency can be improved
```

---

## Architecture

```
┌─────────────────────────────────────────────┐
│              Python Agent (brain)            │
│                                              │
│  agent.py        Main loop, 15s interval     │
│  decision.py     Economic decision engine    │
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
│  POST /cancel         dashboard rejection   │
│  AUTO /tick           30s auto-simulation   │
└──────────────────┬──────────────────────────┘
                   │ WDK SDK
┌──────────────────▼──────────────────────────┐
│     Aave V3 on Polygon (live) or Amoy        │
│     @tetherto/wdk-wallet-evm                 │
│     @tetherto/wdk-protocol-lending-aave-evm  │
└─────────────────────────────────────────────┘
```

---

## Achieved Criterion

| Criterion | What YieldGuard does |
|-----------|----------------------|
| **Technical correctness** | Real WDK SDK calls. `AaveProtocolEvm.supply/repay/withdraw/getAccountData`. Quote-before-execute pattern. Stateful simulation preserves state across restarts. |
| **Agent autonomy** | Runs every 15s without human input. Detects idle funds, danger scenarios, over-collateralization independently. Self-services debt from earned yield automatically. |
| **Economic soundness** | Net Benefit formula on every decision. Live APY from DefiLlama. Gas cost as % of amount. Break-even calculation. Policy engine blocks negative-EV actions. |
| **Real-world applicability** | Configurable policy.json. Reserve buffer prevents wallet drain. Human confirmation gate for write operations. Clear simulation→live migration path (one env var). |



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
SIMULATE=true                    # false for live Polygon Amoy
SEED_PHRASE=your twelve words    # only needed when SIMULATE=false
RPC_URL=https://rpc-amoy.polygon.technology

# .env.agent (optional)
ANTHROPIC_API_KEY=sk-ant-...     # enables Claude AI reasoning
```

### 3. Run
```bash
# Terminal 1
cd wdk-server && node server.js

# Terminal 2
cd agent && python agent.py

# Dashboard: open dashboard/index.html in browser
```

### 4. For GitHub Pages (remote dashboard)

**[Live Dashboard →](https://hvs1012.github.io/yieldguard/?backend=https://barometric-knox-unbreaking.ngrok-free.dev)**

> Dashboard hosted on GitHub Pages. Backend runs locally via ngrok tunnel.
> If the backend appears offline, the ngrok session may have expired.
> Contact for a fresh link or run locally following setup instructions given in 3rd point.

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

**Scenario 4 — Yield self-service:** Let simulation run → wait for `totalEarned > $0.05` → agent autonomously repays debt from earned yield, wallet untouched

---

## Prior Art & Inspiration

- **DeFi Saver** — production health factor automation on Aave
- **Yearn Finance** — automated yield optimization vaults
- **Instadapp** — programmable DeFi accounts with automation
- Autonomous Agents on Blockchains (arxiv.org/abs/2412.02882)
- SoK: Security and Privacy of AI Agents for Blockchain

---

## License

MIT