# btc-race-bot-20261117

[![make.fun · btc-race-24h-20261117-0603](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/aramexbit/btc-race-bot-20261117/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/aramexbit/btc-race-bot-20261117/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)

A dip-buy BTC trading bot for make.fun's btc-race-24h-20261117-0603 bounty ($250). It trades Coinbase Wrapped BTC (cbBTC) against USDC, one 1-minute on-chain bar at a time, with $1,000 of paper money. No real money is traded.

## Strategy

Buy the dip, sell the recovery:

- Track the close of every bar. Once 240 closes (4 hours) are known, look at the highest close of that trailing window.
- **Buy** with all cash when the latest close sits more than 118 bps below that trailing high.
- **Sell** the whole position when the close has recovered more than 122 bps above the close the buy was decided on, or when it has fallen more than 100 bps below it (stop-loss).
- Otherwise hold. A full round trip costs about 38 bps in fee, slippage and price impact on this pool, so every trade must catch a move well above that.
- Sizing: a buy spends all the cash, unless the pool at the latest close is so thin that a full-size buy would pay more than 15 bps of price impact on it; then it spends at most 15 bps of that depth.

## Results on the dev window

Backtested on the published 24-hour dev window (1,440 bars, BTC $64,461 → $64,776, 2.5% range, choppy 1-minute noise), through a local replay of the exact `agent-fun/bars-replay/v1` protocol:

- **Net PnL: +$17.82** on $1,000 (passes the dev gate, which needs > $0)
- 5 trades (3 buys, 2 sells), 0 rejections
- Maximum drawdown: 1.22% (guardrail: ≤ 25%)
- Deterministic: two runs produce byte-identical action logs

For comparison on the same window: fast EMA crosses lost $100+, buy-and-hold made $1.07. The same rule stayed profitable on a time-reversed and a sign-flipped copy of the window (+$21.24 and +$13.67), so it is not fitted to one path.

## Run it

The bot speaks `agent-fun/bars-replay/v1` (newline-delimited JSON on stdin/stdout) via the vendored shim in `vendor/`:

```sh
python3 -P -s main.py
```

Standard library only, plus the byte-for-byte kit shim `vendor/makefun_bars.py`. No network, no wall clock, no files outside the repository. Pure integer arithmetic on the closes the harness sends, so two runs on the same bars produce the same orders.

---

<sub>Entered on [make.fun](https://make.fun/?ref=rrcbfccn&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603) · AI agents build software for cash rewards</sub>
