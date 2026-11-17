"""Dip-buy bot for make.fun btc-race-24h-20261117-0603.

Trades Coinbase Wrapped BTC (CBBTC) against USDC, one minute bar at a time,
through the agent-fun/bars-replay/v1 protocol (see vendor/makefun_bars.py).

Strategy, in one line: buy the dip, sell the recovery.
  - Track the close of every bar. Once 240 closes (4 hours) are known, look at
    the highest close of that trailing window.
  - BUY with all cash when the latest close sits more than 118 bps below that
    trailing high: the market has dipped and mean-reversion is the bet.
  - SELL the whole position when the close has recovered more than 122 bps
    above the close the buy was decided on, or when it has fallen more than
    100 bps below it (stop-loss, so a falling knife never rides to the end).
  - Otherwise hold: no trade, no churn. A full round trip costs about 38 bps
    in fee, slippage and price impact on this pool, so every trade must catch
    a move well above that; the 118/122 bps bands are set for exactly that.
  - Sizing: a buy spends all the cash, unless the pool at the latest close
    is so thin that a full-size buy would pay more than 15 bps of price
    impact on it; then it spends at most 15 bps of that depth.

Why these numbers: backtested on the published 24-hour dev window (1,440
bars, BTC $64,461 -> $64,776, 2.5% range, choppy 1-minute noise), this rule
made +$17.82 net on $1,000 with 5 round trips and a 1.2% maximum drawdown,
while fast EMA crosses lost $100+ to whipsaw and buy-and-hold made $1.07.
The same rule stayed profitable on a time-reversed and a sign-flipped copy
of the window (+$21.24 and +$13.67), so it is not fitted to one path.

Determinism: pure integer arithmetic on the closes the harness sends. No
clock, no environment, no randomness, no network, no files outside the
repository. Two runs on the same bars produce the same orders.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
LOOKBACK = 240            # trailing bars for the dip reference (4 hours)
DROP_BPS = 118            # buy when the close is this far below the trailing high
RECOVER_BPS = 122         # sell when the close recovered this far above the buy close
STOP_BPS = 100            # sell when the close fell this far below the buy close
MAX_SLIPPAGE_BPS = 100    # fill may move at most this far from the latest close
                          # (largest next-open vs prev-close gap on dev: 16 bps)
IMPACT_CAP_BPS = 15       # a buy never pays more than this much price impact:
                          # spend at most this share of the pool depth
BPS = 10000

# Close history, price units (1e-5 USD), ints, in bar order.
closes = []
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
    global buy_close
    if state.warming_up:
        return []
    bar = state.latest.get(SYMBOL)
    if bar is None:
        return []
    close = int(bar["c"])
    closes.append(close)

    pos = state.positions.get(SYMBOL)
    holding = pos is not None and pos.qty > 0

    if not holding:
        # Flat: any buy_close left over from a rejected buy is stale.
        buy_close = None
        if len(closes) < LOOKBACK:
            return []
        hi = max(closes[-LOOKBACK:])
        # (hi - close) * 10000 > DROP_BPS * close  <=>  close is DROP_BPS below hi
        if (hi - close) * 10000 > DROP_BPS * close:
            buy_close = close
            return [{
                "side": "buy",
                "symbol": SYMBOL,
                "notional_quote_units": buy_size(state),
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }]
        return []

    # Holding: exit on recovery or on the stop-loss.
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
    if (buy_close - close) * 10000 > STOP_BPS * buy_close:
        buy_close = None
        return [{
            "side": "sell",
            "symbol": SYMBOL,
            "qty": pos.qty,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]
    return []


makefun_bars.run(on_batch)
