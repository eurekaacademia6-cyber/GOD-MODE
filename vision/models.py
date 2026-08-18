from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple, Optional


@dataclass
class Candle:
    x_center: float
    body_left: float
    body_right: float
    body_top: float
    body_bottom: float
    high: float
    low: float
    open_px: float
    close_px: float
    bullish: bool
    body_pixels: int
    confidence: float
    is_current: bool = False
    track_id: int = -1
    track_age: int = 0
    track_missed: int = 0
    track_state: str = "NEW"
    first_seen_frame: int = 0
    last_seen_frame: int = 0

    @property
    def range_px(self) -> float:
        return max(1.0, self.low - self.high)

    @property
    def body_size_px(self) -> float:
        return abs(self.close_px - self.open_px)

    @property
    def upper_wick_px(self) -> float:
        return max(
            0.0,
            min(self.open_px, self.close_px) - self.high
        )

    @property
    def lower_wick_px(self) -> float:
        return max(
            0.0,
            self.low - max(self.open_px, self.close_px)
        )

    @property
    def close_position(self) -> float:
        denom = max(1.0, self.low - self.high)
        return (self.low - self.close_px) / denom


@dataclass
class Detection:
    candles: List[Candle] = field(default_factory=list)
    quality: float = 0.0
    message: str = "No chart detected."
    roi: Tuple[int, int, int, int] = (0, 0, 0, 0)
    current_index: int = -1
    current_price_y: Optional[float] = None
    price_proxy_ready: bool = False
    volume_available: bool = False
    higher_timeframe_available: bool = False

    @property
    def usable(self) -> bool:
        return (
            len(self.candles) >= 10
            and self.quality >= 0.60
            and self.current_index >= 0
        )


@dataclass
class IndicatorSnapshot:
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    stochastic_k: Optional[float] = None
    stochastic_d: Optional[float] = None
    cci: Optional[float] = None
    williams_r: Optional[float] = None

    ema9: Optional[float] = None
    ema21: Optional[float] = None
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    adx: Optional[float] = None

    ichimoku_tenkan: Optional[float] = None
    ichimoku_kijun: Optional[float] = None
    ichimoku_span_a: Optional[float] = None
    ichimoku_span_b: Optional[float] = None

    bb_middle: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    atr: Optional[float] = None
    volatility_regime: str = "UNKNOWN"

    support: Optional[float] = None
    resistance: Optional[float] = None
    supply_zone: Optional[Tuple[float, float]] = None
    demand_zone: Optional[Tuple[float, float]] = None
    vwap: Optional[float] = None

    fib_382: Optional[float] = None
    fib_500: Optional[float] = None
    fib_618: Optional[float] = None

    pivot: Optional[float] = None
    pivot_r1: Optional[float] = None
    pivot_s1: Optional[float] = None

    structure: str = "UNKNOWN"
    candle_pattern_score: float = 0.0
    candle_momentum: float = 0.0
    rejection_score: float = 0.0
    consecutive_bullish: int = 0
    consecutive_bearish: int = 0


@dataclass
class AnalysisComponent:
    name: str
    probability_up: float
    weight: float
    reason: str = ""
    available: bool = True

    @property
    def direction(self) -> str:
        if not self.available:
            return "N/A"
        return "UP" if self.probability_up >= 0.5 else "DOWN"


@dataclass
class Signal:
    label: str
    up_probability: float
    confidence: float
    agreement: float
    components: List[AnalysisComponent] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    blocked_reason: str = ""
    no_trade_reasons: List[str] = field(default_factory=list)
    horizon_seconds: int = 30
    current_reference: str = "CURRENT VISIBLE PRICE"
    expected_move_norm: float = 0.0
    diagnostics: dict = field(default_factory=dict)

    @property
    def down_probability(self) -> float:
        return 1.0 - self.up_probability
