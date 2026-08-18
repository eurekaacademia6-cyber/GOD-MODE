from __future__ import annotations

import json
import os
import queue
import socket
import threading
import time
import traceback

from analysis.engine import AnalysisEngine
from audit import SessionAudit
from capture import WindowCapture, find_window
from runtime_config import RuntimeConfig
from timing import CandleClock
from vision.detector import CandleDetector, DetectorConfig
from vision.models import Candle
from vision.tracker import CandleTracker

CONFIG = RuntimeConfig()

def log_error(text):
    try:
        folder = os.path.join(
            os.path.expanduser("~"),
            "AppData", "Local", "QuotexVisionAI", "logs"
        )
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "worker.log"), "a", encoding="utf-8") as f:
            f.write("\n" + "="*70 + "\n" + time.strftime("%Y-%m-%d %H:%M:%S") + "\n" + text + "\n")
    except Exception:
        pass

def connect_worker(host, port):
    last = None
    for _ in range(50):
        try:
            s = socket.create_connection((host, port), timeout=1.2)
            s.settimeout(0.5)
            return s
        except OSError as exc:
            last = exc
            time.sleep(0.1)
    raise ConnectionError(f"Unable to connect to GUI: {last}")

class Sender:
    def __init__(self, sock):
        self.sock = sock
        self.stop = threading.Event()
        self.q = queue.Queue(maxsize=CONFIG.ipc_queue_size)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def send(self, payload, priority=False):
        if self.stop.is_set():
            return False
        try:
            if priority:
                self.q.put(payload, timeout=0.25)
                return True
            try:
                self.q.put_nowait(payload)
                return True
            except queue.Full:
                try:
                    self.q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self.q.put_nowait(payload)
                    return True
                except queue.Full:
                    return False
        except Exception:
            return False

    def _run(self):
        while not self.stop.is_set():
            try:
                payload = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                raw = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
                self.sock.sendall(raw)
            except Exception as exc:
                log_error("IPC sender stopped: " + repr(exc))
                self.stop.set()

    def close(self):
        self.stop.set()
        try:
            self.thread.join(timeout=0.7)
        except Exception:
            pass

def candle_dict(c):
    return {
        "track_id": int(c.track_id), "track_age": int(c.track_age),
        "track_state": str(c.track_state), "is_current": bool(c.is_current),
        "confidence": float(c.confidence), "bullish": bool(c.bullish),
        "body_left": float(c.body_left), "body_right": float(c.body_right),
        "body_top": float(c.body_top), "body_bottom": float(c.body_bottom),
        "high": float(c.high), "low": float(c.low),
        "open_px": float(c.open_px), "close_px": float(c.close_px),
        "body_size_px": float(c.body_size_px),
        "upper_wick_px": float(c.upper_wick_px),
        "lower_wick_px": float(c.lower_wick_px),
        "close_position": float(c.close_position),
        "last_seen_frame": int(c.last_seen_frame),
    }

def signal_dict(s):
    if s is None:
        return None
    return {
        "label": str(s.label),
        "up_probability": float(s.up_probability),
        "down_probability": float(s.down_probability),
        "confidence": float(s.confidence),
        "agreement": float(s.agreement),
        "horizon_seconds": int(s.horizon_seconds),
        "reasons": list(s.reasons),
        "no_trade_reasons": list(s.no_trade_reasons),
        "components": [
            {
                "name": str(c.name),
                "probability_up": float(c.probability_up),
                "direction": str(c.direction),
                "weight": float(c.weight),
                "available": bool(c.available),
                "reason": str(c.reason),
            } for c in s.components
        ],
        "diagnostics": getattr(s, "diagnostics", {}) or {},
    }

def build_runtime():
    detector = CandleDetector(
        DetectorConfig(
            min_candles=10,
            max_candles=30,
            min_body_width_px=2,
        )
    )
    tracker = CandleTracker(
        max_match_distance=42.0,
        max_missed=3,
        history_limit=120,
    )
    return detector, tracker, AnalysisEngine(), CandleClock(30, 0)

def run_self_test(seconds=10):
    detector, tracker, engine, clock = build_runtime()
    start=time.monotonic()
    frames=0
    last_ids=None
    while time.monotonic()-start < seconds:
        frames += 1
        candles=[]
        for i in range(18):
            bull=(i%3)!=0
            base=100.0+i*0.15
            candles.append(Candle(
                x_center=i*22, body_left=i*22-4, body_right=i*22+4,
                body_top=20, body_bottom=60, high=10, low=70,
                open_px=base+(0.25 if bull else -0.15),
                close_px=base+(0.45 if bull else -0.35),
                bullish=bull, pixel_count=100, confidence=0.95
            ))
        rep=tracker.update(candles)
        ids=[c.track_id for c in rep.candles]
        if last_ids is not None and ids != last_ids:
            raise RuntimeError("Tracker identity instability in self-test.")
        last_ids=ids
        if len(rep.candles)>=10:
            engine.analyze(rep.candles, 0.90, timeframe_minutes=0.5)
        time.sleep(0.04)
    assert frames >= 80
    print(json.dumps({"ok":True,"frames":frames,"tracker":True}))
    return 0

def run_worker(host, port):
    sock=connect_worker(host, port)
    sender=Sender(sock)
    audit=SessionAudit()
    detector,tracker,engine,clock=build_runtime()
    capture=None
    frame_id=0
    last_current=-1
    fps=CONFIG.target_fps
    errors=0
    last_hb=0.0

    sender.send({"type":"worker_ready","version":CONFIG.version,"pid":os.getpid(),"fps":fps}, priority=True)

    try:
        while True:
            cycle=time.perf_counter()
            frame_id += 1

            if time.monotonic()-last_hb >= 1.0:
                if not sender.send({"type":"heartbeat","frame_id":frame_id,"fps":round(fps,2)}, priority=True):
                    return 11
                last_hb=time.monotonic()

            try:
                hwnd=find_window("Quotex")
                if not hwnd:
                    sender.send({"type":"status","status":"QUOTEX WINDOW NOT FOUND","frame_id":frame_id}, priority=True)
                    time.sleep(0.5)
                    continue

                if capture is None:
                    capture=WindowCapture()

                cap_start=time.perf_counter()
                frame,rect=capture.capture_window(hwnd)
                cap_ms=(time.perf_counter()-cap_start)*1000

                det_start=time.perf_counter()
                detection=detector.detect(frame,(0.06,0.18,0.99,0.97))
                det_ms=(time.perf_counter()-det_start)*1000

                tr_start=time.perf_counter()
                tracking=tracker.update(detection.candles)
                tr_ms=(time.perf_counter()-tr_start)*1000

                detection.candles=tracking.candles
                detection.current_index=len(tracking.candles)-1 if tracking.candles else -1

                analysis_start=time.perf_counter()
                signal=None
                if (
                    detection.usable
                    and detection.quality>=CONFIG.min_detection_quality
                    and tracking.tracking_stability>=CONFIG.min_tracking_stability
                    and tracking.candles
                    and tracking.candles[-1].track_age>=CONFIG.min_current_age
                ):
                    signal=engine.analyze(
                        detection.candles,
                        detection.quality,
                        timeframe_minutes=clock.timeframe_seconds/60.0,
                        volume_available=False,
                        higher_tf_available=False
                    )
                analysis_ms=(time.perf_counter()-analysis_start)*1000

                current=tracking.current_track_id
                event=None
                if last_current>=0 and current>=0 and current!=last_current:
                    closed=next((c for c in detection.candles if c.track_id==last_current),None)
                    event={"closed_track_id":last_current}
                    if closed is not None:
                        event["closed_candle"]=candle_dict(closed)
                        audit.record(
                            "CANDLE_CLOSED",
                            track_id=closed.track_id,
                            state="CLOSED",
                            direction="BULL" if closed.bullish else "BEAR",
                            vision_confidence=f"{closed.confidence:.4f}",
                            tracking_age=closed.track_age,
                            tracking_stability=f"{tracking.tracking_stability:.4f}",
                            detection_quality=f"{detection.quality:.4f}"
                        )
                last_current=current

                total_ms=(time.perf_counter()-cycle)*1000
                if total_ms>230:
                    fps=max(CONFIG.min_fps,fps-0.5)
                elif total_ms<110:
                    fps=min(CONFIG.max_fps,fps+0.25)

                payload={
                    "type":"frame","version":CONFIG.version,
                    "frame_id":frame_id,"window_rect":list(rect),
                    "detected_count":len(detection.candles),
                    "detection_quality":float(detection.quality),
                    "tracking_stability":float(tracking.tracking_stability),
                    "stable_tracks":int(tracking.stable_tracks),
                    "new_tracks":int(tracking.new_tracks),
                    "recovered_tracks":int(tracking.recovered_tracks),
                    "current_track_id":int(tracking.current_track_id),
                    "candles":[candle_dict(c) for c in detection.candles],
                    "signal":signal_dict(signal),
                    "clock":{"start":clock.formatted()[0],"end":clock.formatted()[1],"remaining":clock.formatted()[2]},
                    "health":{
                        "capture_ms":round(cap_ms,1),"detect_ms":round(det_ms,1),
                        "track_ms":round(tr_ms,1),"analysis_ms":round(analysis_ms,1),
                        "total_ms":round(total_ms,1),"effective_fps":round(fps,2),
                        "worker_errors":errors,"pid":os.getpid()
                    },
                    "candle_event":event
                }

                if not sender.send(payload):
                    pass

                elapsed=time.perf_counter()-cycle
                time.sleep(max(0.02,1.0/fps-elapsed))

            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
                return 12
            except Exception:
                errors += 1
                capture=None
                log_error(traceback.format_exc())
                sender.send({"type":"frame_error","frame_id":frame_id,"error":traceback.format_exc()},priority=True)
                time.sleep(0.35)
    finally:
        sender.close()
        try: sock.close()
        except Exception: pass
