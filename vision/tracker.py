from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import statistics
from vision.models import Candle


@dataclass
class TrackState:
    track_id: int
    last_candle: Candle
    age: int = 1
    missed: int = 0
    first_frame: int = 0
    last_frame: int = 0
    history: List[Tuple[float, float, float, float]] = field(default_factory=list)


@dataclass
class TrackingReport:
    candles: List[Candle]
    current_track_id: int
    tracked_count: int
    new_tracks: int
    recovered_tracks: int
    stable_tracks: int
    tracking_stability: float
    frame_id: int


class CandleTracker:
    def __init__(self, max_match_distance: float = 40.0, max_missed: int = 3, history_limit: int = 120):
        self.max_match_distance = max_match_distance
        self.max_missed = max_missed
        self.history_limit = history_limit
        self.frame_id = 0
        self.next_id = 1
        self.tracks: Dict[int, TrackState] = {}
        self.last_stability = 0.0

    def _estimate_shift(self, previous, current):
        if not previous or not current:
            return 0.0
        prev_sorted = sorted(previous, key=lambda t: t.last_candle.x_center)
        cur_sorted = sorted(current, key=lambda c: c.x_center)
        n = min(len(prev_sorted), len(cur_sorted))
        diffs = [
            cur_sorted[i].x_center - prev_sorted[i].last_candle.x_center
            for i in range(n)
        ]
        return float(statistics.median(diffs)) if diffs else 0.0

    @staticmethod
    def _distance(candle, track, shift):
        old = track.last_candle
        dx = abs(candle.x_center - (old.x_center + shift))
        dw = abs(
            (candle.body_right - candle.body_left)
            - (old.body_right - old.body_left)
        )
        dy = abs(
            ((candle.body_top + candle.body_bottom) / 2.0)
            - ((old.body_top + old.body_bottom) / 2.0)
        )
        direction_penalty = 7.0 if candle.bullish != old.bullish else 0.0
        return dx + 0.40 * dw + 0.08 * dy + direction_penalty

    def _new_track(self, candle):
        tid = self.next_id
        self.next_id += 1
        candle.track_id = tid
        candle.track_age = 1
        candle.track_missed = 0
        candle.track_state = "NEW"
        candle.first_seen_frame = self.frame_id
        candle.last_seen_frame = self.frame_id
        return TrackState(
            tid, candle, 1, 0,
            self.frame_id, self.frame_id,
            [(candle.open_px, candle.high, candle.low, candle.close_px)],
        )

    def update(self, candles):
        self.frame_id += 1
        visible = sorted(list(candles), key=lambda c: c.x_center)
        previous = [t for t in self.tracks.values() if t.missed <= self.max_missed]
        shift = self._estimate_shift(previous, visible)

        pairs = []
        for track in previous:
            for idx, candle in enumerate(visible):
                pairs.append((self._distance(candle, track, shift), track.track_id, idx))
        pairs.sort(key=lambda x: x[0])

        used_tracks = set()
        used_candles = set()
        new_tracks = 0
        recovered = 0

        for dist, tid, idx in pairs:
            if dist > self.max_match_distance or tid in used_tracks or idx in used_candles:
                continue
            track = self.tracks[tid]
            candle = visible[idx]
            if track.missed > 0:
                recovered += 1
            used_tracks.add(tid)
            used_candles.add(idx)

            candle.track_id = tid
            candle.track_age = track.age + 1
            candle.track_missed = 0
            candle.track_state = "TRACKED"
            candle.first_seen_frame = track.first_frame
            candle.last_seen_frame = self.frame_id

            track.last_candle = candle
            track.age += 1
            track.missed = 0
            track.last_frame = self.frame_id
            track.history.append(
                (candle.open_px, candle.high, candle.low, candle.close_px)
            )
            track.history = track.history[-self.history_limit:]

        for idx, candle in enumerate(visible):
            if idx in used_candles:
                continue
            state = self._new_track(candle)
            self.tracks[state.track_id] = state
            new_tracks += 1

        for tid, track in list(self.tracks.items()):
            if tid not in used_tracks and track.last_frame != self.frame_id:
                track.missed += 1
                if track.missed > self.max_missed:
                    del self.tracks[tid]

        current_id = -1
        if visible:
            for c in visible:
                c.is_current = False
            visible[-1].is_current = True
            visible[-1].track_state = "CURRENT"
            current_id = visible[-1].track_id

        stable = sum(1 for c in visible if c.track_age >= 3 and c.track_missed == 0)
        stability = stable / len(visible) if visible else 0.0
        self.last_stability = stability

        return TrackingReport(
            candles=visible,
            current_track_id=current_id,
            tracked_count=len(visible),
            new_tracks=new_tracks,
            recovered_tracks=recovered,
            stable_tracks=stable,
            tracking_stability=stability,
            frame_id=self.frame_id,
        )

    def get_track_history(self, track_id):
        state = self.tracks.get(track_id)
        return list(state.history) if state else []
