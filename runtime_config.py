from dataclasses import dataclass

@dataclass(frozen=True)
class RuntimeConfig:
    version: str = "5.4-GOD-MODE"
    target_fps: float = 6.0
    min_fps: float = 2.0
    max_fps: float = 8.0
    min_detection_quality: float = 0.68
    min_tracking_stability: float = 0.72
    min_current_age: int = 3
    worker_timeout_seconds: float = 6.0
    restart_initial_seconds: float = 0.5
    restart_max_seconds: float = 8.0
    ipc_queue_size: int = 2
