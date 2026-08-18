from __future__ import annotations

import numpy as np

from analysis.indicators import build_snapshot
from vision.models import AnalysisComponent, Candle, Signal


def sigmoid(x: float) -> float:
    x = float(max(-8.0, min(8.0, x)))
    return float(1.0 / (1.0 + np.exp(-x)))


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def centered_probability(score: float) -> float:
    return sigmoid(score)


class AnalysisEngine:
    """
    Symmetric next-candle ensemble.

    Every layer produces a centered score where:
      positive = bullish
      negative = bearish

    The final probability is built from the weighted mean of those centered
    scores. This avoids the previous tendency to drift toward UP just because
    several probability values started around 0.50.
    """

    def analyze(
        self,
        candles,
        quality,
        timeframe_minutes=1,
        volume_available=False,
        higher_tf_available=False,
    ):
        if len(candles) < 10:
            return Signal(
                "NO TRADE",
                0.50,
                0.0,
                0.0,
                blocked_reason="Fewer than 10 reliable candles.",
                no_trade_reasons=["INSUFFICIENT_CANDLES"],
            )

        if quality < 0.60:
            return Signal(
                "NO TRADE",
                0.50,
                0.0,
                0.0,
                blocked_reason="Vision quality is below threshold.",
                no_trade_reasons=["LOW_VISION_QUALITY"],
            )

        s = build_snapshot(candles)
        last = candles[-1]
        avg_range = max(
            1.0,
            float(np.mean([c.range_px for c in candles[-10:] ]))
        )

        components = []

        # ---------------- L1 Candle Vision ----------------
        direction = 1.0 if last.bullish else -1.0
        body_strength = clamp(last.body_size_px / avg_range, 0.0, 2.0)
        candle_score = (
            0.80 * direction * body_strength
            + 0.55 * s.candle_momentum
            + 0.55 * s.rejection_score
            + 0.40 * s.candle_pattern_score
        )

        if s.consecutive_bullish >= 3:
            candle_score += 0.20
        if s.consecutive_bearish >= 3:
            candle_score -= 0.20

        components.append(
            AnalysisComponent(
                "L1 Candle Vision",
                centered_probability(candle_score),
                1.25,
                "OHLC, body/wick, momentum, streak, rejection",
            )
        )

        # ---------------- L2 Momentum ----------------
        momentum_score = 0.0

        if s.rsi is not None:
            # Treat RSI >70 as overbought/reversal pressure rather than
            # blindly bullish, while 50-70 provides trend momentum.
            if s.rsi >= 70:
                momentum_score -= 0.35
            elif s.rsi <= 30:
                momentum_score += 0.35
            else:
                momentum_score += clamp(
                    (s.rsi - 50.0) / 20.0,
                    -1.0,
                    1.0,
                ) * 0.60

        if s.macd_hist is not None:
            momentum_score += clamp(
                s.macd_hist / avg_range,
                -2.0,
                2.0,
            ) * 0.55

        if s.stochastic_k is not None and s.stochastic_d is not None:
            cross = (s.stochastic_k - s.stochastic_d) / 20.0
            momentum_score += clamp(cross, -1.0, 1.0) * 0.40

        if s.cci is not None:
            momentum_score += clamp(
                s.cci / 200.0,
                -1.0,
                1.0,
            ) * 0.30

        if s.williams_r is not None:
            # -20 = overbought, -80 = oversold.
            momentum_score += clamp(
                -(s.williams_r + 50.0) / 30.0,
                -1.0,
                1.0,
            ) * 0.25

        components.append(
            AnalysisComponent(
                "L2 Momentum",
                centered_probability(momentum_score),
                1.20,
                "RSI, MACD, Stochastic, CCI, Williams %R",
            )
        )

        # ---------------- L3 Trend ----------------
        trend_score = 0.0

        for value, weight in [
            (s.ema9, 0.30),
            (s.ema21, 0.28),
            (s.ema50, 0.22),
            (s.ema200, 0.20),
        ]:
            if value is not None:
                trend_score += (
                    weight
                    * clamp(
                        (last.close_px - value) / avg_range,
                        -2.0,
                        2.0,
                    )
                )

        if s.adx is not None and s.adx >= 20:
            if s.ema9 is not None and s.ema21 is not None:
                trend_score += (
                    0.30
                    * (1.0 if s.ema9 > s.ema21 else -1.0)
                )

        if (
            s.ichimoku_span_a is not None
            and s.ichimoku_span_b is not None
        ):
            cloud_top = max(
                s.ichimoku_span_a,
                s.ichimoku_span_b,
            )
            cloud_bottom = min(
                s.ichimoku_span_a,
                s.ichimoku_span_b,
            )

            if last.close_px > cloud_top:
                trend_score += 0.35
            elif last.close_px < cloud_bottom:
                trend_score -= 0.35

        if s.structure == "HH_HL_BULL":
            trend_score += 0.60
        elif s.structure == "LH_LL_BEAR":
            trend_score -= 0.60

        components.append(
            AnalysisComponent(
                "L3 Trend",
                centered_probability(trend_score),
                1.30,
                "EMA 9/21/50/200, ADX, Ichimoku, structure",
            )
        )

        # ---------------- L4 Volatility ----------------
        vol_score = 0.0

        if s.volatility_regime == "EXPANSION":
            vol_score += 0.12 * np.sign(s.candle_momentum)
        elif s.volatility_regime == "COMPRESSION":
            vol_score -= 0.04 * np.sign(s.candle_momentum)

        if (
            s.bb_upper is not None
            and s.bb_lower is not None
            and s.bb_middle is not None
        ):
            if last.close_px > s.bb_upper:
                vol_score += 0.18 * np.sign(s.candle_momentum)
            elif last.close_px < s.bb_lower:
                vol_score += 0.18 * np.sign(s.candle_momentum)

            band_width = max(
                1.0,
                s.bb_upper - s.bb_lower,
            )
            vol_score += clamp(
                s.candle_momentum
                / (band_width / max(avg_range, 1.0)),
                -1.0,
                1.0,
            ) * 0.12

        components.append(
            AnalysisComponent(
                "L4 Volatility",
                centered_probability(vol_score),
                0.80,
                "Bollinger Bands, ATR, volatility regime",
            )
        )

        # ---------------- L5 Levels ----------------
        level_score = 0.0

        if s.support is not None and s.resistance is not None:
            ds = abs(last.close_px - s.support)
            dr = abs(last.close_px - s.resistance)

            # Near support -> bullish reaction bias.
            if ds <= avg_range * 0.75:
                level_score += 0.45
            # Near resistance -> bearish reaction bias.
            if dr <= avg_range * 0.75:
                level_score -= 0.45

        if s.demand_zone is not None:
            lo, hi = s.demand_zone
            if lo <= last.close_px <= hi:
                level_score += 0.40

        if s.supply_zone is not None:
            lo, hi = s.supply_zone
            if lo <= last.close_px <= hi:
                level_score -= 0.40

        if s.vwap is not None:
            level_score += (
                0.20
                * np.sign(
                    last.close_px - s.vwap
                )
            )

        nearby_fibs = [
            f
            for f in (
                s.fib_382,
                s.fib_500,
                s.fib_618,
            )
            if f is not None
        ]

        for fib in nearby_fibs:
            if abs(last.close_px - fib) <= avg_range * 0.20:
                level_score += (
                    0.06
                    * np.sign(
                        s.candle_momentum
                    )
                )

        if s.pivot is not None:
            level_score += (
                0.12
                * np.sign(
                    last.close_px - s.pivot
                )
            )

        components.append(
            AnalysisComponent(
                "L5 Levels",
                centered_probability(level_score),
                0.95,
                "S/R, supply/demand, VWAP, Fibonacci, pivots",
            )
        )

        # ---------------- L6 Confirmation ----------------
        base_centered = [
            (c.probability_up - 0.5) * 2.0
            for c in components
        ]

        base_mean = float(np.mean(base_centered)) if base_centered else 0.0
        directional_agreement = (
            sum((score >= 0) == (base_mean >= 0) for score in base_centered)
            / len(base_centered)
            if base_centered else 0.0
        )

        confirmation_score = (
            0.65 * base_mean
            + 0.35 * ((directional_agreement * 2.0) - 1.0)
        )

        components.append(
            AnalysisComponent(
                "L6 Confirmation",
                centered_probability(confirmation_score),
                0.75,
                "Cross-layer agreement and confirmation gates",
            )
        )

        centered_scores = [
            (c.probability_up - 0.5) * 2.0
            for c in components
        ]

        weights = [
            c.weight
            for c in components
        ]

        combined_score = float(
            np.average(
                centered_scores,
                weights=weights,
            )
        )

        p_up = centered_probability(
            combined_score * 2.2
        )

        up = p_up >= 0.5

        agreement = (
            sum(
                (
                    score >= 0
                ) == up
                for score in centered_scores
            )
            / len(centered_scores)
        )

        trend_score = centered_scores[2]
        momentum_score = centered_scores[1]

        trend_momentum_agree = (
            (trend_score >= 0)
            == (momentum_score >= 0)
        )

        edge = abs(p_up - 0.5) * 2.0

        confidence = clamp(
            0.46 * edge
            + 0.30 * agreement
            + 0.24 * quality,
            0.0,
            1.0,
        )

        no_trade = []

        # Availability is reported, not falsely simulated.
        if not volume_available:
            no_trade.append(
                "VOLUME_NOT_READ_FROM_SCREEN"
            )

        if not higher_tf_available:
            no_trade.append(
                "MULTI_TF_NOT_LOADED"
            )

        if not trend_momentum_agree:
            no_trade.append(
                "TREND_MOMENTUM_CONFLICT"
            )

        if agreement < 0.67:
            no_trade.append(
                "LAYER_DISAGREEMENT"
            )

        if edge < 0.18:
            no_trade.append(
                "WEAK_DIRECTIONAL_EDGE"
            )

        if confidence < 0.62:
            no_trade.append(
                "LOW_CONFIDENCE"
            )

        label = "NO TRADE"

        if (
            confidence >= 0.62
            and agreement >= 0.67
            and edge >= 0.18
            and trend_momentum_agree
        ):
            label = "UP" if up else "DOWN"

        reasons = [
            (
                f"{c.name}: "
                f"{'UP' if c.probability_up >= 0.5 else 'DOWN'} "
                f"{c.probability_up * 100:.0f}%"
            )
            for c in components
        ]

        diagnostics = {
            "rsi": s.rsi,
            "macd": s.macd,
            "macd_signal": s.macd_signal,
            "macd_hist": s.macd_hist,
            "stoch_k": s.stochastic_k,
            "stoch_d": s.stochastic_d,
            "cci": s.cci,
            "williams_r": s.williams_r,
            "ema9": s.ema9,
            "ema21": s.ema21,
            "ema50": s.ema50,
            "ema200": s.ema200,
            "adx": s.adx,
            "ichimoku_tenkan": s.ichimoku_tenkan,
            "ichimoku_kijun": s.ichimoku_kijun,
            "ichimoku_span_a": s.ichimoku_span_a,
            "ichimoku_span_b": s.ichimoku_span_b,
            "bb_middle": s.bb_middle,
            "bb_upper": s.bb_upper,
            "bb_lower": s.bb_lower,
            "atr": s.atr,
            "volatility_regime": s.volatility_regime,
            "support": s.support,
            "resistance": s.resistance,
            "vwap": s.vwap,
            "fib_382": s.fib_382,
            "fib_500": s.fib_500,
            "fib_618": s.fib_618,
            "pivot": s.pivot,
            "pivot_r1": s.pivot_r1,
            "pivot_s1": s.pivot_s1,
            "structure": s.structure,
            "consecutive_bullish": s.consecutive_bullish,
            "consecutive_bearish": s.consecutive_bearish,
            "rejection_score": s.rejection_score,
            "candle_momentum": s.candle_momentum,
            "combined_score": combined_score,
            "edge": edge,
            "trend_momentum_agree": trend_momentum_agree,
            "timeframe_minutes": timeframe_minutes,
        }

        return Signal(
            label=label,
            up_probability=p_up,
            confidence=confidence,
            agreement=agreement,
            components=components,
            reasons=reasons,
            no_trade_reasons=no_trade,
            diagnostics=diagnostics,
        )
