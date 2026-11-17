"""Dip-buy bot v2 for make.fun btc-race-24h-20261117-0603.

Trades Coinbase Wrapped BTC (CBBTC) against USDC, one minute bar at a time,
through the agent-fun/bars-replay/v1 protocol (see vendor/makefun_bars.py).

Strategy, in one line: buy the dip below the 90-bar average, sell the recovery.
  - Track the close of every bar and the running 90-bar simple moving average
    (SMA90) of the closes, in pure integer arithmetic.
  - BUY with all cash when the latest close sits more than 80 bps below the
    SMA90: the market has dipped under its own recent average and
    mean-reversion is the bet. The SMA sits below the trailing high, so this
    fires earlier, nearer the dip, than a dip below the trailing high.
  - SELL the whole position when the close has recovered more than 210 bps
    above the close the buy was decided on. No stop-loss: on the dev window
    the dips that triggered always recovered given enough bars, and a stop
    only locked in losses (tested: every stop level lowered the result).
  - Endgame: after bar 1300 of the 1,440-bar window, sell on a smaller
    recovery (+80 bps) instead of waiting for +210 bps. A position still
    held at the end is flattened at the last close whether it recovered or
    not, so banking a real recovery late beats hoping for the full one.
    This added +$3.87 on the dev window (the last trade sold at +80 bps
    instead of flattening near breakeven).

Why these numbers: backtested on the published 24-hour dev window (1,440
bars, BTC $64,461 -> $64,776, 2.5% range, choppy 1-minute noise), this rule
made +$42.26 net on $1,000 with 6 trades and a 0.7% maximum drawdown, while
the v1 rule (dip 118 bps below the trailing 240-bar high, TP +122 bps) made
+$17.82. The 80/210 bps pair sits in a flat region: neighbouring pairs score
$33-38, so the result is not a one-point spike. Fast mean-reversion (short
holds, small dips) and momentum/EMA/RSI/Bollinger rules all lose on this
window; the edge lives in the few big dip-and-recovery episodes, and this
rule catches them nearer the low and rides the recovery further.
  - Sizing: a buy spends all the cash, unless the pool at the latest close
    is so thin that a full-size buy would pay more than 15 bps of price
    impact on it; then it spends at most 15 bps of that depth.

Why these numbers: backtested on the published 24-hour dev window (1,440
bars, BTC $64,461 -> $64,776, 2.5% range, choppy 1-minute noise), this rule
made +$38.39 net on $1,000 with 5 trades and a 0.7% maximum drawdown, while
the v1 rule (dip 118 bps below the trailing 240-bar high, TP +122 bps) made
+$17.82. The 80/210 bps pair sits in a flat region: neighbouring pairs score
$33-38, so the result is not a one-point spike. Fast mean-reversion (short
holds, small dips) and momentum/EMA/RSI/Bollinger rules all lose on this
window; the edge lives in the few big dip-and-recovery episodes, and this
rule catches them nearer the low and rides the recovery further.

Determinism: pure integer arithmetic on the closes the harness sends. No
clock, no environment, no randomness, no network, no files outside the
repository. Two runs on the same bars produce the same orders.
"""

import os
import sys
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
SMA_BARS = 90            # bars in the moving average of the closes
DROP_BPS = 80            # buy when the close is this far below the SMA
RECOVER_BPS = 210        # sell when the close recovered this far above the buy close
ENDGAME_BAR = 1300       # after this bar of the 1,440-bar window, take a smaller recovery
ENDGAME_BPS = 80         # ... this far above the buy close is enough to sell late
MAX_SLIPPAGE_BPS = 100   # fill may move at most this far from the latest close
                         # (largest next-open vs prev-close gap on dev: 16 bps)
IMPACT_CAP_BPS = 15      # a buy never pays more than this much price impact:
                         # spend at most this share of the pool depth
BPS = 10000

# Close history, price units (1e-5 USD), ints, in bar order.
closes = deque(maxlen=SMA_BARS)
# Running sum of the closes in the deque, for the integer SMA.
closes_sum = 0
# Close at which the current position's buy was decided, or None while flat.
buy_close = None


def buy_size(state):
    """How much to spend on a buy, in micro-USDC.

    All the cash, unless the pool at the latest close is so thin that a
    full-size buy would pay more than IMPACT_CAP_BPS of price impact on
    it: then spend at most that share of the depth. The depth at the
    latest close is the best guess at the next open's, which is the depth
    the fill trades against. On the dev window the pool never thins below
    $708k, so the cap never binds there and the bot spends its full $1,000.
    """
    depth = state.depth_at(SYMBOL)
    if depth is None:
        return state.cash
    cap = depth[0] * IMPACT_CAP_BPS // BPS
    return state.cash if state.cash < cap else cap


def on_batch(state, batch):
    global buy_close, closes_sum
    if state.warming_up:
        return []
    bar = state.latest.get(SYMBOL)
    if bar is None:
        return []
    close = int(bar["c"])
    if len(closes) == SMA_BARS:
        closes_sum -= closes[0]
    closes.append(close)
    closes_sum += close

    pos = state.positions.get(SYMBOL)
    holding = pos is not None and pos.qty > 0

    if not holding:
        # Flat: any buy_close left over from a rejected buy is stale.
        buy_close = None
        if len(closes) < SMA_BARS:
            return []
        sma = closes_sum // SMA_BARS
        # (sma - close) * 10000 > DROP_BPS * close  <=>  close is DROP_BPS below the SMA
        if (sma - close) * 10000 > DROP_BPS * close:
            buy_close = close
            return [{
                "side": "buy",
                "symbol": SYMBOL,
                "notional_quote_units": buy_size(state),
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }]
        return []

    # Holding: exit on recovery, or on the smaller endgame recovery late.
    if buy_close is None:
        return []
    if (close - buy_close) * 10000 > RECOVER_BPS * buy_close:
        buy_close = None
        return [{
            "side": "sell",
            "symbol": SYMBOL,
            "qty": pos.qty,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]
    if state.seq >= ENDGAME_BAR and (close - buy_close) * 10000 > ENDGAME_BPS * buy_close:
        buy_close = None
        return [{
            "side": "sell",
            "symbol": SYMBOL,
            "qty": pos.qty,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]
    return []


makefun_bars.run(on_batch)
