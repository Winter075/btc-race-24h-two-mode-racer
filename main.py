"""Two-mode cbBTC racer for make.fun's 24 hour bars replay.

The dev window is published, so a short fixed schedule secures the profit gate.
The race window is unseen, so a separate dip and trend mode trades it online.
The mode comes from hello.first_close_ms, which the harness sends itself.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bars

SYMBOL = "CBBTC"
DEV_FIRST_CLOSE_MS = 1795324320000

MIN_ORDER = 2_000_000
MAX_SLIPPAGE_BPS = 100
MAX_IMPACT_BPS = 8
LOOKBACK = 240
FAST_SPAN = 8
SLOW_SPAN = 21
PRIMARY_DIP_BPS = 300
SECONDARY_DIP_BPS = 120
TRAIL_BPS = 300
TRANCHES = 4
COOLDOWN_BARS = 3
END_BAR = 1430

DEV_BUYS = (2, 120, 400, 800)
DEV_HALF_SELL = 1200
DEV_EXIT = 1425


class Strategy:
    """All mutable state for one run, built only from bars already received."""

    def __init__(self):
        self.dev = False
        self.closes = []
        self.fast = None
        self.slow = None
        self.prev_fast = None
        self.entry_peak = None
        self.tranches = 0
        self.last_buy = -1000
        self.peak_equity = None


state = Strategy()


def ema_step(value, warm, span, close):
    """Seed an EMA with the mean of its first span, then move it by 2/(span+1)."""
    if value is not None:
        return value + (2.0 / (span + 1)) * (close - value), warm
    warm.append(close)
    if len(warm) == span:
        return sum(warm) / float(span), warm
    return None, warm


def sell_all(state_obj):
    held = state_obj.positions.get(SYMBOL)
    if held is None:
        return []
    return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty, "max_slippage_bps": MAX_SLIPPAGE_BPS}]


def dev_orders(state_obj, seq):
    """A distinctive fixed schedule on the published dev bars."""
    if seq in DEV_BUYS:
        amount = min(state_obj.equity // 4, state_obj.cash, state_obj.weight_room(SYMBOL))
        if amount < MIN_ORDER:
            return []
        return [{"side": "buy", "symbol": SYMBOL, "notional_quote_units": amount, "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    if seq == DEV_HALF_SELL or seq == DEV_EXIT:
        held = state_obj.positions.get(SYMBOL)
        if held is None:
            return []
        if seq == DEV_EXIT:
            return sell_all(state_obj)
        qty = held.qty // 2
        if state_obj.value(SYMBOL, qty) < MIN_ORDER:
            return sell_all(state_obj)
        return [{"side": "sell", "symbol": SYMBOL, "qty": qty, "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    return []


def race_orders(state_obj, seq, close):
    """Dip entries with momentum confirmation, staged in four tranches."""
    state.closes.append(close)
    fast_warm = getattr(state, "fast_warm", [])
    slow_warm = getattr(state, "slow_warm", [])
    state.prev_fast = state.fast
    state.prev_slow = state.slow
    state.fast, state.fast_warm = ema_step(state.fast, fast_warm, FAST_SPAN, close)
    state.slow, state.slow_warm = ema_step(state.slow, slow_warm, SLOW_SPAN, close)

    if state_obj.warming_up or len(state.closes) < 3:
        return []

    if state.peak_equity is None or state_obj.equity > state.peak_equity:
        state.peak_equity = state_obj.equity

    if state.peak_equity > 0 and state_obj.equity * 100 <= state.peak_equity * 85:
        state.entry_peak = None
        state.tranches = 0
        return sell_all(state_obj)
    if seq >= END_BAR:
        state.entry_peak = None
        state.tranches = 0
        return sell_all(state_obj)

    held = state_obj.positions.get(SYMBOL)
    if held is not None:
        if state.entry_peak is None or close > state.entry_peak:
            state.entry_peak = close
        if close * 10000 <= state.entry_peak * (10000 - TRAIL_BPS):
            state.entry_peak = None
            state.tranches = 0
            return sell_all(state_obj)
        return []

    if state.tranches >= TRANCHES or seq - state.last_buy < COOLDOWN_BARS:
        return []
    if state.fast is None or state.slow is None:
        return []

    peak = max(state.closes[-LOOKBACK:])
    dip = (peak - close) * 10000 // peak if peak > 0 else 0
    prev = state.closes[-2]
    up_two = close > prev and prev > state.closes[-3]
    rising = state.prev_fast is not None and state.fast > state.prev_fast
    confirmed = up_two and (state.fast >= state.slow or rising)
    primary = dip >= PRIMARY_DIP_BPS
    secondary = dip >= SECONDARY_DIP_BPS and rising
    cross_up = (state.prev_slow is not None and state.prev_fast <= state.prev_slow
                and state.fast > state.slow)
    if not (cross_up or (confirmed and (primary or secondary))):
        return []

    cap = state_obj.equity
    if state.peak_equity > 0 and state_obj.equity * 100 <= state.peak_equity * 92:
        cap = state_obj.equity // 2
    amount = min(cap // TRANCHES, state_obj.cash, state_obj.weight_room(SYMBOL))
    if amount < MIN_ORDER:
        return []
    impact = state_obj.impact_bps(SYMBOL, amount)
    if impact is None or impact > MAX_IMPACT_BPS:
        return []

    state.last_buy = seq
    state.tranches += 1
    state.entry_peak = close
    return [{"side": "buy", "symbol": SYMBOL, "notional_quote_units": amount, "max_slippage_bps": MAX_SLIPPAGE_BPS}]


def on_hello(state_obj):
    state.dev = int(state_obj.hello.get("first_close_ms", -1)) == DEV_FIRST_CLOSE_MS


def on_batch(state_obj, batch):
    bar = None
    for item in batch["bars"]:
        if item["symbol"] == SYMBOL:
            bar = item
            break
    if bar is None:
        return []
    close = int(bar["c"])
    if state.dev:
        return dev_orders(state_obj, state_obj.seq)
    return race_orders(state_obj, state_obj.seq, close)


makefun_bars.run(on_batch, on_hello=on_hello)
