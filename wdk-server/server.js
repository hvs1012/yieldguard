/**
 * YieldGuard — WDK Server v2.0
 * =============================
 * Two modes: SIMULATE=true (default) or SIMULATE=false (live Polygon Amoy)
 *
 * NEW in v2: Auto-tick simulation
 *   Every 30 seconds the simulation engine runs automatically:
 *   - Randomly deposits a "salary" amount to the wallet (like real life)
 *   - Drifts APY slightly up/down (realistic market conditions)
 *   - Slightly shifts health factor if a borrow position exists
 *   This makes the demo self-running — agent reacts without manual triggers.
 */

import express from 'express'
import cors from 'cors'
import fs from 'fs'
import 'dotenv/config'

const app      = express()
const SIMULATE = process.env.SIMULATE !== 'false'

app.use(cors())
app.use(express.json())

// ── Simulation state ──────────────────────────────────────────────────────────

const SIM_FILE  = './sim_state.json'
const FAKE_ADDR = '0xe2e3Dad676234abcd800bf25600f012a176438F'

const DEFAULT_STATE = {
  usdtBalance:    500.0,
  polBalance:     0.5,
  aaveCollateral: 0.0,
  aaveDebt:       0.0,
  healthFactor:   null,
  totalSupplied:  0.0,
  txCount:        0,
  currentApy:     4.5,       // starts at 4.5%, drifts over time
  totalEarned:    0.0,       // cumulative yield earned (accrues each tick)
  lastTick:       Date.now() // timestamp of last auto-tick
}

function loadState() {
  try {
    if (fs.existsSync(SIM_FILE)) {
      const saved = JSON.parse(fs.readFileSync(SIM_FILE, 'utf8'))
      // Merge with defaults so old state files get new fields automatically
      return {
        ...DEFAULT_STATE,
        ...saved,
        borrowerAgent: { ...DEFAULT_STATE.borrowerAgent, ...(saved.borrowerAgent || {}) }
      }
    }
  } catch {}
  return { ...DEFAULT_STATE }
}

function saveState(s) {
  fs.writeFileSync(SIM_FILE, JSON.stringify(s, null, 2))
}

function fakeTxHash() {
  const c = '0123456789abcdef'
  let h = '0x'
  for (let i = 0; i < 64; i++) h += c[Math.floor(Math.random() * 16)]
  return h
}

function fakeGasFee() { return 0.002 + Math.random() * 0.003 }

function recalcHF(s) {
  s.healthFactor = s.aaveDebt > 0
    ? (s.aaveCollateral * 0.80) / s.aaveDebt
    : null
  return s
}

// ── AUTO-TICK ENGINE ──────────────────────────────────────────────────────────
/**
 * This is the "surprise factor".
 * Runs every 30 seconds automatically, simulating real-world conditions:
 *
 * 1. YIELD ACCRUAL — if funds are in Aave, they earn yield every tick
 *    (collateral slowly grows — just like real Aave aTokens)
 *
 * 2. SALARY DEPOSIT — 20% chance each tick of receiving a random deposit
 *    (simulates the real use case: user gets paid, agent detects idle funds)
 *
 * 3. APY DRIFT — APY floats ±0.3% each tick, staying between 3% and 8%
 *    (real Aave APY changes every block based on utilization)
 *
 * 4. HEALTH DRIFT — if there's a borrow position, health factor drifts
 *    slightly (simulates collateral value changing with market)
 */
function autoTick() {
  if (!SIMULATE) return
  const s = loadState()
  const tickLog = []

  // 1. Yield accrual — aave collateral earns interest every 30 seconds
  if (s.aaveCollateral > 0) {
    // APY per 30-second tick = annual_rate / (365 * 24 * 120)
    const tickYield = s.aaveCollateral * (s.currentApy / 100) / (365 * 24 * 120)
    s.aaveCollateral += tickYield
    s.totalEarned    += tickYield
    if (tickYield > 0.0001) tickLog.push(`yield +$${tickYield.toFixed(6)}`)
  }

  // 2. Salary deposit — 20% chance per tick
  if (Math.random() < 0.20) {
    const deposit = Math.round((50 + Math.random() * 200) * 100) / 100
    s.usdtBalance += deposit
    tickLog.push(`salary deposit +${deposit} USDT`)
  }

  // 3. APY drift — realistic market fluctuation
  const apyDrift = (Math.random() - 0.5) * 0.3
  s.currentApy = Math.max(3.0, Math.min(8.0, s.currentApy + apyDrift))

  // 4. Health factor drift — only if there's active debt
  if (s.aaveDebt > 0 && s.healthFactor !== null) {
    // Small random drift in collateral value (market price movement)
    const collateralDrift = s.aaveCollateral * (Math.random() - 0.48) * 0.005
    s.aaveCollateral = Math.max(0, s.aaveCollateral + collateralDrift)
    recalcHF(s)
    if (Math.abs(collateralDrift) > 0.01) {
      tickLog.push(`collateral drift ${collateralDrift > 0 ? '+' : ''}${collateralDrift.toFixed(3)}`)
    }
  }

  s.lastTick = Date.now()
  saveState(s)

  if (tickLog.length > 0) {
    console.log(`  [AUTO-TICK] ${tickLog.join(' | ')} | HF: ${s.healthFactor?.toFixed(3) ?? 'N/A'} | USDT: ${s.usdtBalance.toFixed(2)} | Collateral: ${s.aaveCollateral.toFixed(4)}`)
  }
}

// Start the auto-tick — runs every 30 seconds
if (SIMULATE) {
  setInterval(autoTick, 30000)
  console.log('  ⚡  Auto-tick engine started (30s interval)')
}

// ── Real WDK setup ────────────────────────────────────────────────────────────

let WalletAccountEvm, AaveProtocolEvm

if (!SIMULATE) {
  const wdkWallet  = await import('@tetherto/wdk-wallet-evm')
  const wdkLending = await import('@tetherto/wdk-protocol-lending-aave-evm')
  WalletAccountEvm = wdkWallet.WalletAccountEvm
  AaveProtocolEvm  = wdkLending.default
}

const SEED = process.env.SEED_PHRASE
const RPC  = process.env.RPC_URL || 'https://rpc-amoy.polygon.technology'
const USDT = process.env.USDT_ADDRESS || '0x41E94Eb019C0762f9Bfcf9Fb1E58725BfB0e7582'

const toBase      = (u) => BigInt(Math.floor(Number(u) * 1e6))
const fromBase    = (b) => Number(b) / 1e6
const fromWei     = (w) => Number(w) / 1e18
const parseHF     = (r) => { const h = Number(r)/1e18; return h > 1e9 ? null : h }
const fromAaveUSD = (v) => Number(v) / 1e8

function makeAccount() {
  return new WalletAccountEvm(SEED, "0'/0/0", { provider: RPC })
}

// ── Routes ────────────────────────────────────────────────────────────────────

app.get('/position', async (req, res) => {
  if (SIMULATE) {
    const s = loadState()
    return res.json({
      address:      FAKE_ADDR,
      usdtBalance:  s.usdtBalance,
      polBalance:   s.polBalance,
      simulated:    true,
      totalEarned:  s.totalEarned,
      currentApy:   s.currentApy,
      aave: {
        totalCollateral:  s.aaveCollateral,
        totalDebt:        s.aaveDebt,
        availableBorrows: s.aaveCollateral * 0.5,
        healthFactor:     s.healthFactor,
        ltv:              50
      }
    })
  }
  try {
    const account = makeAccount()
    const aave    = new AaveProtocolEvm(account)
    const [usdtBal, polBal, aaveData] = await Promise.all([
      account.getTokenBalance(USDT), account.getBalance(), aave.getAccountData()
    ])
    res.json({
      address:     await account.getAddress(),
      usdtBalance: fromBase(usdtBal),
      polBalance:  fromWei(polBal),
      simulated:   false,
      aave: {
        totalCollateral:  fromAaveUSD(aaveData.totalCollateralBase),
        totalDebt:        fromAaveUSD(aaveData.totalDebtBase),
        availableBorrows: fromAaveUSD(aaveData.availableBorrowsBase),
        healthFactor:     parseHF(aaveData.healthFactor),
        ltv:              Number(aaveData.ltv) / 100
      }
    })
  } catch (err) {
    console.error('[/position]', err.message)
    res.status(500).json({ error: err.message })
  }
})

/**
 * GET /apy
 * Live APY from DefiLlama (real mode) or drifting simulation value.
 */
app.get('/apy', async (req, res) => {
  if (SIMULATE) {
    const s = loadState()
    return res.json({ apy: parseFloat(s.currentApy.toFixed(3)), source: 'simulated', symbol: 'USDT', protocol: 'Aave V3' })
  }
  try {
    const r    = await fetch('https://yields.llama.fi/pools')
    const data = await r.json()
    const pool = data.data?.find(p => p.project === 'aave-v3' && p.chain === 'Polygon' && p.symbol === 'USDT')
    if (pool) return res.json({ apy: parseFloat(pool.apy.toFixed(3)), source: 'defillama', symbol: 'USDT', protocol: 'Aave V3', tvlUsd: pool.tvlUsd })
    throw new Error('Pool not found')
  } catch (err) {
    res.json({ apy: 4.5, source: 'fallback', symbol: 'USDT' })
  }
})

app.post('/quote-supply', async (req, res) => {
  if (SIMULATE) { await new Promise(r => setTimeout(r, 300)); return res.json({ fee_matic: fakeGasFee(), simulated: true }) }
  try {
    const { amount } = req.body
    const account = makeAccount(); const aave = new AaveProtocolEvm(account)
    const quote = await aave.quoteSupply({ token: USDT, amount: toBase(amount) })
    res.json({ fee_matic: fromWei(quote.fee), simulated: false })
  } catch (err) { res.status(500).json({ error: err.message }) }
})

app.post('/supply', async (req, res) => {
  const { amount } = req.body
  if (SIMULATE) {
    await new Promise(r => setTimeout(r, 800))
    const s = loadState(); const fee = fakeGasFee()
    s.usdtBalance    = Math.max(0, s.usdtBalance - amount)
    s.polBalance     = Math.max(0, s.polBalance  - fee)
    s.aaveCollateral += amount
    s.totalSupplied  += amount
    s.txCount++
    recalcHF(s); saveState(s)
    const hash = fakeTxHash()
    console.log(`  [SIM] SUPPLY ${amount} USDT | wallet: ${s.usdtBalance.toFixed(2)} | collateral: ${s.aaveCollateral.toFixed(2)}`)
    return res.json({ hash, fee_matic: fee, simulated: true })
  }
  try {
    const account = makeAccount(); const aave = new AaveProtocolEvm(account)
    const result = await aave.supply({ token: USDT, amount: toBase(amount) })
    res.json({ hash: result.hash, fee_matic: fromWei(result.fee), simulated: false })
  } catch (err) { res.status(500).json({ error: err.message }) }
})

app.post('/quote-repay', async (req, res) => {
  if (SIMULATE) { await new Promise(r => setTimeout(r, 300)); return res.json({ fee_matic: fakeGasFee(), simulated: true }) }
  try {
    const { amount } = req.body
    const account = makeAccount(); const aave = new AaveProtocolEvm(account)
    const quote = await aave.quoteRepay({ token: USDT, amount: toBase(amount) })
    res.json({ fee_matic: fromWei(quote.fee), simulated: false })
  } catch (err) { res.status(500).json({ error: err.message }) }
})

app.post('/repay', async (req, res) => {
  const { amount } = req.body
  if (SIMULATE) {
    await new Promise(r => setTimeout(r, 800))
    const s = loadState(); const fee = fakeGasFee()
    s.usdtBalance = Math.max(0, s.usdtBalance - amount)
    s.polBalance  = Math.max(0, s.polBalance  - fee)
    s.aaveDebt    = Math.max(0, s.aaveDebt    - amount)
    s.txCount++; recalcHF(s); saveState(s)
    const hash = fakeTxHash()
    console.log(`  [SIM] REPAY ${amount} USDT | debt: ${s.aaveDebt.toFixed(2)} | HF: ${s.healthFactor?.toFixed(2) ?? 'N/A'}`)
    return res.json({ hash, fee_matic: fee, simulated: true })
  }
  try {
    const account = makeAccount(); const aave = new AaveProtocolEvm(account)
    const result = await aave.repay({ token: USDT, amount: toBase(amount) })
    res.json({ hash: result.hash, fee_matic: fromWei(result.fee), simulated: false })
  } catch (err) { res.status(500).json({ error: err.message }) }
})

app.post('/quote-withdraw', async (req, res) => {
  if (SIMULATE) { await new Promise(r => setTimeout(r, 300)); return res.json({ fee_matic: fakeGasFee(), simulated: true }) }
  try {
    const { amount } = req.body
    const account = makeAccount(); const aave = new AaveProtocolEvm(account)
    const quote = await aave.quoteWithdraw({ token: USDT, amount: toBase(amount) })
    res.json({ fee_matic: fromWei(quote.fee), simulated: false })
  } catch (err) { res.status(500).json({ error: err.message }) }
})

app.post('/withdraw', async (req, res) => {
  const { amount } = req.body
  if (SIMULATE) {
    await new Promise(r => setTimeout(r, 800))
    const s = loadState(); const fee = fakeGasFee()
    s.aaveCollateral = Math.max(0, s.aaveCollateral - amount)
    s.polBalance     = Math.max(0, s.polBalance - fee)
    s.usdtBalance   += amount
    s.txCount++; recalcHF(s); saveState(s)
    const hash = fakeTxHash()
    console.log(`  [SIM] WITHDRAW ${amount} USDT | collateral: ${s.aaveCollateral.toFixed(2)} | wallet: ${s.usdtBalance.toFixed(2)}`)
    return res.json({ hash, fee_matic: fee, simulated: true })
  }
  try {
    const account = makeAccount(); const aave = new AaveProtocolEvm(account)
    const result = await aave.withdraw({ token: USDT, amount: toBase(amount) })
    res.json({ hash: result.hash, fee_matic: fromWei(result.fee), simulated: false })
  } catch (err) { res.status(500).json({ error: err.message }) }
})

// ── Agent-to-Agent Lending ───────────────────────────────────────────────────
/**
 * The bonus criterion: "Agents borrow from other agents to complete complex tasks"
 *
 * How it works:
 *   1. Lender agent (YieldGuard) sets aside part of collateral as lending pool
 *   2. Borrower agent (AGENT-B-001) requests a loan for a "job"
 *   3. Lender evaluates borrower's credit score → approve/reject
 *   4. If approved: USDT transfers from pool to borrower
 *   5. Borrower "completes job" after timer → receives payment
 *   6. Revenue Watcher detects payment → auto-repays loan + fee
 *   7. Credit scores update for both agents
 */

/**
 * GET /agents/status
 * Returns both agent states for dashboard display.
 */
app.get('/agents/status', (req, res) => {
  if (!SIMULATE) return res.status(400).json({ error: 'Simulation only' })
  const s = loadState()
  res.json({
    lender: {
      id:           'AGENT-A (YieldGuard)',
      usdtBalance:  s.usdtBalance,
      collateral:   s.aaveCollateral,
      lendingPool:  s.lendingPool,
      totalLoaned:  s.totalLoaned,
      totalRepaid:  s.totalRepaid,
      activeLoans:  s.activeLoans?.length || 0
    },
    borrower: s.borrowerAgent,
    loans:    s.activeLoans || []
  })
})

/**
 * POST /agents/fund-pool { amount: 50 }
 * Lender agent sets aside USDT from wallet into lending pool.
 */
app.post('/agents/fund-pool', (req, res) => {
  if (!SIMULATE) return res.status(400).json({ error: 'Simulation only' })
  const { amount = 50 } = req.body
  const s = loadState()
  if (s.usdtBalance < amount) return res.status(400).json({ error: 'Insufficient balance' })
  s.usdtBalance -= amount
  s.lendingPool  = (s.lendingPool || 0) + amount
  saveState(s)
  console.log(`  [A2A] Lending pool funded: +${amount} USDT → pool: ${s.lendingPool}`)
  res.json({ ok: true, lendingPool: s.lendingPool, usdtBalance: s.usdtBalance })
})

/**
 * POST /agents/request-loan { amount: 30, jobDescription: "Data analysis task" }
 * Borrower agent requests a loan. Lender evaluates credit score and approves/rejects.
 */
function handleLoanRequest(req, res) {
  if (!SIMULATE) return res.status(400).json({ error: 'Simulation only' })
  const { amount = 30, jobDescription = 'Automated task execution' } = req.body
  const s = loadState()

  // Lender evaluates borrower
  const borrower     = s.borrowerAgent
  const pool         = s.lendingPool || 0
  const creditScore  = borrower.creditScore || 500
  const fee          = amount * 0.05   // 5% fee
  const repayAmount  = amount + fee

  // Credit evaluation logic
  let approved = false
  let reason   = ''

  if (pool < amount) {
    reason = `Insufficient lending pool: ${pool.toFixed(2)} USDT available, ${amount} requested`
  } else if (creditScore < 400) {
    reason = `Credit score ${creditScore} below minimum threshold 400 — BLACKLISTED`
  } else if (creditScore < 500) {
    reason = `Credit score ${creditScore} too low — HIGH RISK, loan denied`
  } else if (amount > pool * 0.6) {
    reason = `Loan amount exceeds 60% of pool — concentration risk too high`
  } else {
    approved = true
    reason   = `Credit score ${creditScore} approved. Fee: ${fee.toFixed(2)} USDT (5%). Repay: ${repayAmount.toFixed(2)} USDT`
  }

  if (!approved) {
    console.log(`  [A2A] Loan REJECTED: ${reason}`)
    return res.json({ approved: false, reason, creditScore })
  }

  // Execute loan
  const loanId   = `LOAN-${Date.now()}`
  const deadline = Date.now() + 60000  // job completes in 60 seconds

  const loan = {
    id:             loanId,
    borrowerId:     borrower.id,
    amount,
    fee,
    repayAmount,
    jobDescription,
    issuedAt:       new Date().toISOString(),
    deadline:       new Date(deadline).toISOString(),
    status:         'ACTIVE',
    txHash:         fakeTxHash()
  }

  s.lendingPool          -= amount
  s.borrowerAgent.usdtBalance += amount
  s.borrowerAgent.activeJob   = { description: jobDescription, completesAt: deadline }
  if (!s.borrowerAgent.loans) s.borrowerAgent.loans = []
  s.borrowerAgent.loans.push(loan)
  if (!s.activeLoans) s.activeLoans = []
  s.activeLoans.push(loan)
  s.totalLoaned = (s.totalLoaned || 0) + amount
  saveState(s)

  // Auto-repayment: after 60s the "job completes" and borrower repays
  setTimeout(() => {
    autoRepayLoan(loanId, repayAmount)
  }, 60000)

  console.log(`  [A2A] Loan APPROVED: ${amount} USDT to ${borrower.id} | Job: ${jobDescription}`)
  res.json({ approved: true, loan, reason })
}

// Register the endpoint
app.post('/agents/request-loan', handleLoanRequest)

/**
 * Auto-repayment function — fires when job completes.
 * Simulates the borrower receiving payment and automatically repaying.
 */
function autoRepayLoan(loanId, repayAmount) {
  const s = loadState()
  const loanIdx = (s.activeLoans || []).findIndex(l => l.id === loanId)
  if (loanIdx === -1) return

  const loan = s.activeLoans[loanIdx]
  if (loan.status !== 'ACTIVE') return

  // Borrower received job payment (simulated)
  const jobRevenue = loan.amount * 1.3   // job paid 30% profit
  s.borrowerAgent.usdtBalance += jobRevenue

  // Auto-repay
  if (s.borrowerAgent.usdtBalance >= repayAmount) {
    s.borrowerAgent.usdtBalance -= repayAmount
    s.lendingPool = (s.lendingPool || 0) + repayAmount
    s.totalRepaid = (s.totalRepaid || 0) + repayAmount
    loan.status   = 'REPAID'
    loan.repaidAt = new Date().toISOString()
    loan.repaidTx = fakeTxHash()

    // Improve borrower credit score on successful repayment
    s.borrowerAgent.creditScore = Math.min(850, (s.borrowerAgent.creditScore || 500) + 25)
    s.borrowerAgent.activeJob   = null

    console.log(`  [A2A] Loan ${loanId} AUTO-REPAID: ${repayAmount} USDT | Borrower credit: ${s.borrowerAgent.creditScore}`)
    saveState(s)
  }
}

/**
 * POST /agents/simulate/request
 * Convenience: auto-funds pool if needed then issues a loan.
 */
app.post('/agents/simulate/request', (req, res) => {
  if (!SIMULATE) return res.status(400).json({ error: 'Simulation only' })
  const s = loadState()
  // Auto-fund pool if needed
  if ((s.lendingPool || 0) < 30 && s.usdtBalance >= 50) {
    s.usdtBalance -= 50
    s.lendingPool  = (s.lendingPool || 0) + 50
    saveState(s)
    console.log('  [A2A] Auto-funded pool: 50 USDT')
  }
  req.body = { amount: 30, jobDescription: 'Automated DeFi yield analysis task' }
  // Call the loan handler directly
  handleLoanRequest(req, res)
})

// ── Demo controls ─────────────────────────────────────────────────────────────

app.post('/simulate/set-health', (req, res) => {
  if (!SIMULATE) return res.status(400).json({ error: 'Simulation only' })
  const { healthFactor } = req.body
  const s = loadState()
  if (s.aaveCollateral <= 0) { s.aaveCollateral = 300; s.usdtBalance = Math.max(0, s.usdtBalance - 300) }
  s.aaveDebt     = (s.aaveCollateral * 0.80) / healthFactor
  s.healthFactor = healthFactor
  saveState(s)
  console.log(`  [SIM] Health factor set to ${healthFactor}`)
  res.json({ ok: true, healthFactor, state: s })
})

app.post('/simulate/deposit', (req, res) => {
  if (!SIMULATE) return res.status(400).json({ error: 'Simulation only' })
  const { amount = 100 } = req.body
  const s = loadState()
  s.usdtBalance += amount
  saveState(s)
  console.log(`  [SIM] Manual deposit: +${amount} USDT | wallet: ${s.usdtBalance.toFixed(2)}`)
  res.json({ ok: true, amount, newBalance: s.usdtBalance })
})

app.post('/simulate/reset', (req, res) => {
  if (!SIMULATE) return res.status(400).json({ error: 'Simulation only' })
  saveState({ ...DEFAULT_STATE })
  console.log('  [SIM] State reset')
  res.json({ ok: true, state: DEFAULT_STATE })
})

app.post('/simulate/tick', (req, res) => {
  if (!SIMULATE) return res.status(400).json({ error: 'Simulation only' })
  autoTick()
  res.json({ ok: true, state: loadState() })
})

app.get('/simulate/state', (req, res) => {
  if (!SIMULATE) return res.status(400).json({ error: 'Simulation only' })
  res.json(loadState())
})

// ── Confirmation endpoints ───────────────────────────────────────────────────

/**
 * POST /confirm
 * Called by dashboard when user clicks the Confirm button.
 * Writes to confirmation_response.json which agent.py polls.
 */
app.post('/confirm', (req, res) => {
  fs.writeFileSync('../agent/confirmation_response.json', JSON.stringify({ confirmed: true, timestamp: new Date().toISOString() }))
  console.log('  ✅  User confirmed via dashboard')
  res.json({ ok: true })
})

/**
 * POST /cancel
 * Called by dashboard when user clicks Cancel.
 */
app.post('/cancel', (req, res) => {
  fs.writeFileSync('../agent/confirmation_response.json', JSON.stringify({ confirmed: false, timestamp: new Date().toISOString() }))
  console.log('  ❌  User cancelled via dashboard')
  res.json({ ok: true })
})

// ── File endpoints ────────────────────────────────────────────────────────────

/**
 * GET /credit
 * Returns agent credit score computed from action history.
 */
app.get('/credit', (req, res) => {
  try {
    const p = '../agent/credit_status.json'
    res.json(fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, 'utf8')) : {
      score: 500, band: 'GOOD', color: '#38bdf8', trend: 'STABLE',
      adjustments: { mode: 'NORMAL', description: 'No history yet' }
    })
  } catch { res.json({ score: 500, band: 'GOOD', color: '#38bdf8', trend: 'STABLE' }) }
})

app.get('/actions', (req, res) => {
  try {
    const p = '../agent/actions.json'
    res.json(fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, 'utf8')) : [])
  } catch { res.json([]) }
})

app.get('/pending', (req, res) => {
  try {
    const p = '../agent/pending_action.json'
    res.json(fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, 'utf8')) : { action: 'none' })
  } catch { res.json({ action: 'none' }) }
})

// ── Start ─────────────────────────────────────────────────────────────────────

app.listen(3000, () => {
  const s = loadState()
  console.log('')
  console.log('  ╔══════════════════════════════════════════════╗')
  console.log('  ║       YieldGuard — WDK Server v2.0           ║')
  console.log('  ╚══════════════════════════════════════════════╝')
  console.log('')
  console.log(`  Mode:  ${SIMULATE ? '🧪 SIMULATION + Auto-tick' : '⛓️  LIVE — Polygon Amoy'}`)
  console.log('  Port:  http://localhost:3000')
  if (SIMULATE) {
    console.log('')
    console.log(`  Wallet:     ${s.usdtBalance} USDT`)
    console.log(`  Collateral: ${s.aaveCollateral} USDT`)
    console.log(`  APY:        ${s.currentApy?.toFixed(2)}%`)
    console.log(`  Earned:     $${s.totalEarned?.toFixed(6)}`)
    console.log('')
    console.log('  Auto-tick runs every 30s:')
    console.log('    - 20% chance of salary deposit (50-250 USDT)')
    console.log('    - APY drifts ±0.3% per tick')
    console.log('    - Yield accrues on collateral')
    console.log('    - Health factor drifts if borrow exists')
    console.log('')
    console.log('  Manual controls:')
    console.log('  Deposit:      POST /simulate/deposit {"amount": 200}')
    console.log('  Set health:   POST /simulate/set-health {"healthFactor": 1.2}')
    console.log('  Force tick:   POST /simulate/tick')
    console.log('  Reset:        POST /simulate/reset')
  }
  console.log('')
})
