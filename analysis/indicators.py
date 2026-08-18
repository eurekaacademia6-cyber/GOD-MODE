from __future__ import annotations

import numpy as np

from vision.models import Candle, IndicatorSnapshot


def _arr(values):
    return np.asarray(values, dtype=float)


def ema(values, period):
    values = _arr(values)
    if len(values) == 0:
        return None
    alpha = 2.0 / (period + 1.0)
    value = float(values[0])
    for x in values[1:]:
        value = alpha * float(x) + (1.0 - alpha) * value
    return value


def rsi(closes, period=14):
    closes = _arr(closes)
    if len(closes) < period + 1:
        return None
    delta = np.diff(closes)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    for i in range(period, len(delta)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def macd(closes, fast=12, slow=26, signal=9):
    closes = _arr(closes)
    if len(closes) < slow + signal:
        return None, None, None

    ef = float(closes[0])
    es = float(closes[0])
    af = 2.0 / (fast + 1.0)
    ass = 2.0 / (slow + 1.0)
    line = []

    for x in closes:
        ef = af * float(x) + (1.0 - af) * ef
        es = ass * float(x) + (1.0 - ass) * es
        line.append(ef - es)

    line = np.asarray(line)
    sig = ema(line, signal)
    return float(line[-1]), float(sig), float(line[-1] - sig)


def stochastic(candles, period=14, smooth=3):
    if len(candles) < period:
        return None, None

    def k_at(i):
        w = candles[max(0, i - period + 1):i + 1]
        hh = max(c.high for c in w)
        ll = min(c.low for c in w)
        if hh == ll:
            return 50.0
        return 100.0 * (candles[i].close_px - ll) / (hh - ll)

    k = k_at(len(candles) - 1)
    ks = [k_at(i) for i in range(max(0, len(candles) - smooth), len(candles))]
    return float(k), float(np.mean(ks))


def cci(candles, period=20):
    if len(candles) < period:
        return None
    tp = _arr([(c.high + c.low + c.close_px) / 3.0 for c in candles])
    window = tp[-period:]
    mean = float(np.mean(window))
    dev = float(np.mean(np.abs(window - mean)))
    if dev == 0:
        return 0.0
    return float((tp[-1] - mean) / (0.015 * dev))


def williams_r(candles, period=14):
    if len(candles) < period:
        return None
    w = candles[-period:]
    hh = max(c.high for c in w)
    ll = min(c.low for c in w)
    if hh == ll:
        return -50.0
    return float(-100.0 * (hh - candles[-1].close_px) / (hh - ll))


def atr(candles, period=14):
    if len(candles) < period + 1:
        return None
    tr = []
    for i in range(1, len(candles)):
        c = candles[i]
        p = candles[i - 1]
        tr.append(max(
            c.high - c.low,
            abs(c.high - p.close_px),
            abs(c.low - p.close_px),
        ))
    return float(np.mean(tr[-period:]))


def adx(candles, period=14):
    if len(candles) < period * 2:
        return None
    trs, plus_dm, minus_dm = [], [], []
    for i in range(1, len(candles)):
        c = candles[i]
        p = candles[i - 1]
        up = c.high - p.high
        down = p.low - c.low
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        trs.append(max(
            c.high - c.low,
            abs(c.high - p.close_px),
            abs(c.low - p.close_px),
        ))
    tr = max(1e-9, float(np.mean(trs[-period:])))
    plus = 100.0 * float(np.mean(plus_dm[-period:])) / tr
    minus = 100.0 * float(np.mean(minus_dm[-period:])) / tr
    return float(100.0 * abs(plus - minus) / max(1e-9, plus + minus))


def bollinger(closes, period=20, std_mult=2.0):
    closes = _arr(closes)
    if len(closes) < period:
        return None, None, None
    w = closes[-period:]
    mid = float(np.mean(w))
    sd = float(np.std(w))
    return mid, mid + std_mult * sd, mid - std_mult * sd


def ichimoku(candles):
    if len(candles) < 52:
        return None, None, None, None

    def mid(period):
        w = candles[-period:]
        return (max(c.high for c in w) + min(c.low for c in w)) / 2.0

    tenkan = mid(9)
    kijun = mid(26)
    span_a = (tenkan + kijun) / 2.0
    span_b = mid(52)
    return tenkan, kijun, span_a, span_b


def support_resistance(candles, lookback=30):
    w = candles[-min(lookback, len(candles)):]
    return min(c.low for c in w), max(c.high for c in w)


def supply_demand(candles, lookback=12):
    w = candles[-min(lookback, len(candles)):]
    if not w:
        return None, None
    avg = np.mean([c.range_px for c in w])
    supply = None
    demand = None
    for c in w:
        if c.range_px >= avg * 1.35:
            if c.bullish:
                demand = (min(c.low, c.close_px), max(c.low, c.close_px))
            else:
                supply = (min(c.close_px, c.high), max(c.close_px, c.high))
    return supply, demand


def vwap_proxy(candles):
    # Screen-only analysis does not have true broker volume.
    num = 0.0
    den = 0.0
    for c in candles:
        pseudo_volume = max(1.0, c.body_pixels) * c.confidence
        price = (c.high + c.low + c.close_px) / 3.0
        num += price * pseudo_volume
        den += pseudo_volume
    return None if den == 0 else num / den


def fibonacci(candles):
    if len(candles) < 5:
        return None, None, None
    w = candles[-min(30, len(candles)):]
    hi = max(c.high for c in w)
    lo = min(c.low for c in w)
    d = hi - lo
    return hi - 0.382 * d, hi - 0.500 * d, hi - 0.618 * d


def pivots(candles):
    if len(candles) < 3:
        return None, None, None
    c = candles[-1]
    p = (c.high + c.low + c.close_px) / 3.0
    return p, 2*p-c.low, 2*p-c.high


def structure(candles):
    if len(candles) < 6:
        return "UNKNOWN"
    h0 = candles[-3].high
    h1 = candles[-1].high
    l0 = candles[-3].low
    l1 = candles[-1].low
    if h1 > h0 and l1 > l0:
        return "HH_HL_BULL"
    if h1 < h0 and l1 < l0:
        return "LH_LL_BEAR"
    return "RANGE"


def build_snapshot(candles):
    closes = [c.close_px for c in candles]
    s = IndicatorSnapshot()

    s.rsi = rsi(closes)
    s.macd, s.macd_signal, s.macd_hist = macd(closes)
    s.stochastic_k, s.stochastic_d = stochastic(candles)
    s.cci = cci(candles)
    s.williams_r = williams_r(candles)

    s.ema9 = ema(closes, 9)
    s.ema21 = ema(closes, 21)
    s.ema50 = ema(closes, 50)
    s.ema200 = ema(closes, 200)
    s.adx = adx(candles)

    (
        s.ichimoku_tenkan,
        s.ichimoku_kijun,
        s.ichimoku_span_a,
        s.ichimoku_span_b,
    ) = ichimoku(candles)

    s.bb_middle, s.bb_upper, s.bb_lower = bollinger(closes)
    s.atr = atr(candles)

    if s.atr is not None:
        recent = float(np.mean([c.range_px for c in candles[-5:]]))
        base = float(np.mean([c.range_px for c in candles[-min(20, len(candles)):]]))
        ratio = recent / max(1e-9, base)
        s.volatility_regime = (
            "EXPANSION" if ratio > 1.30
            else "COMPRESSION" if ratio < 0.75
            else "NORMAL"
        )

    s.support, s.resistance = support_resistance(candles)
    s.supply_zone, s.demand_zone = supply_demand(candles)
    s.vwap = vwap_proxy(candles)
    s.fib_382, s.fib_500, s.fib_618 = fibonacci(candles)
    s.pivot, s.pivot_r1, s.pivot_s1 = pivots(candles)
    s.structure = structure(candles)

    bull = 0
    bear = 0
    for c in reversed(candles):
        if c.bullish:
            bull += 1
        else:
            break
    for c in reversed(candles):
        if not c.bullish:
            bear += 1
        else:
            break

    s.consecutive_bullish = bull
    s.consecutive_bearish = bear

    avg_range = max(1.0, float(np.mean([c.range_px for c in candles[-10:]])))
    s.candle_momentum = (candles[-1].close_px - candles[-4].close_px) / avg_range
    s.rejection_score = (
        candles[-1].lower_wick_px - candles[-1].upper_wick_px
    ) / avg_range

    score = 0.75 if candles[-1].bullish else -0.75
    if len(candles) >= 2:
        a = candles[-2]
        b = candles[-1]
        if b.bullish and not a.bullish and b.close_px >= a.open_px:
            score += 0.80
        if not b.bullish and a.bullish and b.close_px <= a.open_px:
            score -= 0.80
    s.candle_pattern_score = score

    return s
