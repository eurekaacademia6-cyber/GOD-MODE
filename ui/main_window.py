from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path

from PySide6.QtCore import (
    QProcess,
    QTimer,
)
from PySide6.QtGui import QColor
from PySide6.QtNetwork import (
    QHostAddress,
    QTcpServer,
    QTcpSocket,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from audit import SessionAudit
from runtime_config import RuntimeConfig
from timing import CandleClock
from ui.overlay import Overlay


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "Quotex Vision AI - Production Live"
        )
        self.resize(1200, 850)

        self.config = RuntimeConfig()
        self.running = False
        self.audit = SessionAudit()
        self.worker = None
        self.worker_socket = None
        self.server = QTcpServer(self)
        self.server.newConnection.connect(
            self._accept_worker
        )

        self.rx_buffer = b""
        self.worker_restarts = 0
        self.last_heartbeat = 0.0
        self.last_frame_id = 0
        self.last_rect = None
        self.last_message_time = 0.0

        self.clock = CandleClock(
            30,
            0,
        )
        self.overlay = Overlay()

        self._build_ui()

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(
            self._update_clock
        )
        self.clock_timer.start(250)

        self.watchdog = QTimer(self)
        self.watchdog.timeout.connect(
            self._watchdog
        )
        self.watchdog.start(1000)

    # =========================================================
    # UI
    # =========================================================
    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)

        title = QLabel(
            "QUOTEX VISION AI — PRODUCTION LIVE TRACKER"
        )
        title.setStyleSheet(
            "font-size:22px;font-weight:800;"
        )
        root.addWidget(title)

        self.live_status = QLabel(
            "READY — PRESS START LIVE"
        )
        self.live_status.setStyleSheet(
            "font-size:15px;font-weight:700;"
        )
        root.addWidget(
            self.live_status
        )

        controls = QHBoxLayout()

        self.start_btn = QPushButton(
            "START LIVE"
        )
        self.start_btn.clicked.connect(
            self.start
        )

        self.stop_btn = QPushButton(
            "STOP"
        )
        self.stop_btn.clicked.connect(
            self.stop
        )

        controls.addWidget(
            self.start_btn
        )
        controls.addWidget(
            self.stop_btn
        )

        self.vision_box = QCheckBox(
            "VISIBLE CANDLE BOXES"
        )
        self.vision_box.setChecked(
            True
        )
        self.vision_box.stateChanged.connect(
            self._toggle_boxes
        )
        controls.addWidget(
            self.vision_box
        )

        self.analysis_box = QCheckBox(
            "LIVE ANALYSIS"
        )
        self.analysis_box.setChecked(
            True
        )
        controls.addWidget(
            self.analysis_box
        )

        controls.addWidget(
            QLabel("Horizon:")
        )

        self.timeframe = QComboBox()
        self.timeframe.addItems([
            "30 seconds",
            "60 seconds",
            "120 seconds",
        ])
        self.timeframe.currentIndexChanged.connect(
            self._timeframe_changed
        )
        controls.addWidget(
            self.timeframe
        )

        controls.addWidget(
            QLabel("Clock:")
        )

        self.offset = QSpinBox()
        self.offset.setRange(
            -120,
            120,
        )
        self.offset.setSuffix(
            " s"
        )
        controls.addWidget(
            self.offset
        )
        self.offset.valueChanged.connect(
            self._offset_changed
        )

        root.addLayout(
            controls
        )

        top = QGridLayout()

        current = QGroupBox(
            "CURRENT CANDLE — TRACKED LIVE"
        )
        cv = QVBoxLayout(current)

        self.current_label = QLabel(
            "Current: —"
        )
        self.current_track = QLabel(
            "Track: —"
        )
        self.current_state = QLabel(
            "State: —"
        )
        self.current_conf = QLabel(
            "Vision: —"
        )
        self.current_time = QLabel(
            "Time: —"
        )
        self.current_remaining = QLabel(
            "Remaining: —"
        )

        for label in (
            self.current_label,
            self.current_track,
            self.current_state,
            self.current_conf,
            self.current_time,
            self.current_remaining,
        ):
            cv.addWidget(label)

        prediction = QGroupBox(
            "NEXT CANDLE / NEXT WINDOW"
        )
        pv = QVBoxLayout(prediction)

        self.prediction_label = QLabel(
            "WAITING"
        )
        self.prediction_label.setStyleSheet(
            "font-size:29px;font-weight:900;"
        )

        self.prediction_probability = QLabel(
            "UP — | DOWN —"
        )
        self.prediction_confidence = QLabel(
            "Confidence —"
        )
        self.prediction_target = QLabel(
            "Window —"
        )
        self.prediction_reference = QLabel(
            "Reference: current visible price"
        )

        for label in (
            self.prediction_label,
            self.prediction_probability,
            self.prediction_confidence,
            self.prediction_target,
            self.prediction_reference,
        ):
            pv.addWidget(label)

        top.addWidget(
            current,
            0,
            0,
        )
        top.addWidget(
            prediction,
            0,
            1,
        )

        root.addLayout(
            top
        )

        tracking = QGroupBox(
            "PERSISTENT CANDLE TRACKING"
        )
        tv = QVBoxLayout(tracking)

        self.tracking_summary = QLabel(
            "Worker: disconnected"
        )
        tv.addWidget(
            self.tracking_summary
        )

        self.table = QTableWidget(
            0,
            10,
        )
        self.table.setHorizontalHeaderLabels([
            "TRACK",
            "STATE",
            "DIR",
            "VISION",
            "AGE",
            "BODY",
            "UP WICK",
            "LOW WICK",
            "CURRENT",
            "FRAME",
        ])
        self.table.setMaximumHeight(270)
        tv.addWidget(
            self.table
        )

        root.addWidget(
            tracking
        )

        audit = QGroupBox(
            "DECISION AUDIT"
        )
        av = QGridLayout(audit)

        self.layer_labels = {}

        for row, name in enumerate([
            "L1 Candle Vision",
            "L2 Momentum",
            "L3 Trend",
            "L4 Volatility",
            "L5 Levels",
            "L6 Confirmation",
        ]):
            left = QLabel(name)
            right = QLabel("WAITING")

            av.addWidget(
                left,
                row,
                0,
            )
            av.addWidget(
                right,
                row,
                1,
            )
            self.layer_labels[name] = right

        root.addWidget(
            audit
        )

        health = QGroupBox(
            "GOD MODE — SYSTEM HEALTH"
        )
        hv = QGridLayout(health)
        self.health_labels = {}

        for col, name in enumerate([
            "Worker", "IPC", "Capture", "Detector", "Tracker"
        ]):
            key = QLabel(name)
            value = QLabel("—")
            hv.addWidget(key, 0, col * 2)
            hv.addWidget(value, 0, col * 2 + 1)
            self.health_labels[name] = value

        for col, name in enumerate([
            "Analysis", "FPS", "Latency", "Frame", "Restarts"
        ]):
            key = QLabel(name)
            value = QLabel("—")
            hv.addWidget(key, 1, col * 2)
            hv.addWidget(value, 1, col * 2 + 1)
            self.health_labels[name] = value

        root.addWidget(
            health
        )

        bottom = QHBoxLayout()

        self.events = QTextEdit()
        self.events.setReadOnly(
            True
        )

        self.diagnostics = QTextEdit()
        self.diagnostics.setReadOnly(
            True
        )

        bottom.addWidget(
            self.events
        )
        bottom.addWidget(
            self.diagnostics
        )

        root.addLayout(
            bottom
        )

        self.setCentralWidget(
            central
        )

    # =========================================================
    # WORKER CONTROL
    # =========================================================
    def start(self):
        if self.running:
            return

        self.running = True
        self.worker_restarts = 0
        self.last_message_time = time.monotonic()

        if not self.server.isListening():
            ok = self.server.listen(
                QHostAddress.LocalHost
            )

            if not ok:
                self.live_status.setText(
                    "IPC SERVER ERROR: "
                    + self.server.errorString()
                )
                self.running = False
                return

        self._start_worker()

    def stop(self):
        self.running = False

        if self.worker_socket is not None:
            try:
                self.worker_socket.disconnectFromHost()
            except Exception:
                pass
            self.worker_socket = None

        if self.worker is not None:
            try:
                self.worker.kill()
            except Exception:
                pass
            self.worker = None

        self.overlay.hide()
        self.live_status.setText(
            "STOPPED"
        )

    def _worker_executable(self):
        if not getattr(
            sys,
            "frozen",
            False,
        ):
            return (
                sys.executable,
                [
                    str(
                        Path(
                            __file__
                        ).resolve().parent.parent
                        / "worker_entry.py"
                    ),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(
                        self.server.serverPort()
                    ),
                ],
            )

        worker = (
            Path(sys.executable)
            .resolve()
            .parent
            / "worker"
            / "QuotexVisionAI-Worker.exe"
        )

        return (
            str(worker),
            [
                "--host",
                "127.0.0.1",
                "--port",
                str(
                    self.server.serverPort()
                ),
            ],
        )

    def _start_worker(self):
        if not self.running:
            return

        program, args = (
            self._worker_executable()
        )

        if getattr(
            sys,
            "frozen",
            False,
        ):
            if not Path(program).exists():
                self.live_status.setText(
                    "WORKER EXE NOT FOUND"
                )
                self.events.append(
                    "Expected:\n"
                    + program
                )
                return

        if self.worker is not None:
            try:
                if self.worker.state() != QProcess.NotRunning:
                    return
            except Exception:
                pass

        self.worker = QProcess(
            self
        )

        self.worker.setProcessChannelMode(
            QProcess.SeparateChannels
        )

        self.worker.readyReadStandardError.connect(
            self._worker_stderr
        )
        self.worker.errorOccurred.connect(
            self._worker_error
        )
        self.worker.finished.connect(
            self._worker_finished
        )

        self.worker.start(
            program,
            args,
        )

        self.live_status.setText(
            "WORKER STARTING..."
        )

    # =========================================================
    # IPC
    # =========================================================
    def _accept_worker(self):
        while self.server.hasPendingConnections():
            sock = (
                self.server.nextPendingConnection()
            )

            if self.worker_socket is not None:
                try:
                    self.worker_socket.disconnectFromHost()
                except Exception:
                    pass

            self.worker_socket = sock
            self.rx_buffer = b""

            sock.readyRead.connect(
                self._read_socket
            )
            sock.disconnected.connect(
                self._socket_disconnected
            )

            self.live_status.setText(
                "WORKER CONNECTED"
            )

    def _read_socket(self):
        if self.worker_socket is None:
            return

        self.rx_buffer += bytes(
            self.worker_socket.readAll()
        )

        while b"\n" in self.rx_buffer:
            raw, self.rx_buffer = (
                self.rx_buffer.split(
                    b"\n",
                    1,
                )
            )

            raw = raw.strip()

            if not raw:
                continue

            try:
                message = json.loads(
                    raw.decode(
                        "utf-8",
                        errors="replace",
                    )
                )
            except Exception as exc:
                self.events.append(
                    "IPC JSON ERROR: "
                    + str(exc)
                )
                continue

            self.last_message_time = (
                time.monotonic()
            )

            self._handle_message(
                message
            )

    def _socket_disconnected(self):
        self.worker_socket = None

        if self.running:
            self.live_status.setText(
                "WORKER DISCONNECTED — RESTARTING"
            )
            QTimer.singleShot(
                500,
                self._restart_worker,
            )

    def _worker_stderr(self):
        if self.worker is None:
            return

        raw = bytes(
            self.worker.readAllStandardError()
        )

        if raw:
            self.events.append(
                "WORKER STDERR:\n"
                + raw.decode(
                    "utf-8",
                    errors="replace",
                ).strip()
            )

    def _worker_error(self, error):
        self.live_status.setText(
            "WORKER PROCESS ERROR"
        )

        self.events.append(
            f"Worker process error: {error}"
        )

    def _worker_finished(
        self,
        exit_code,
        exit_status,
    ):
        if not self.running:
            return

        self.worker_restarts += 1

        self.events.append(
            "Worker exited: "
            f"code={exit_code}, "
            f"status={exit_status}"
        )

        QTimer.singleShot(
            500,
            self._restart_worker,
        )

    def _restart_worker(self):
        if not self.running:
            return

        try:
            if self.worker is not None:
                self.worker.kill()
        except Exception:
            pass

        self.worker = None

        self._start_worker()

    # =========================================================
    # MESSAGE HANDLING
    # =========================================================
    def _handle_message(
        self,
        message,
    ):
        kind = message.get(
            "type"
        )

        if kind == "worker_ready":
            self.live_status.setText(
                "WORKER READY • LIVE"
            )
            self.tracking_summary.setText(
                "Worker PID "
                f"{message.get('pid')} • "
                f"FPS {message.get('fps')} • "
                f"Version {message.get('version')}"
            )
            return

        if kind == "heartbeat":
            self.tracking_summary.setText(
                "Worker heartbeat • "
                f"Frame {message.get('frame_id')}"
            )
            return

        if kind == "status":
            self.live_status.setText(
                message.get(
                    "status",
                    "WORKER STATUS",
                )
            )
            return

        if kind == "frame_error":
            self.live_status.setText(
                "FRAME ERROR — WORKER CONTINUES"
            )

            self.events.append(
                message.get(
                    "error",
                    "unknown frame error",
                )
            )
            return

        if kind == "frame":
            self._handle_frame(
                message
            )

    def _handle_frame(
        self,
        message,
    ):
        self.last_frame_id = int(
            message.get(
                "frame_id",
                0,
            )
        )

        self._update_health(
            message
        )

        self.last_rect = tuple(
            message.get(
                "window_rect",
                [0, 0, 1, 1],
            )
        )

        candles = message.get(
            "candles",
            [],
        )

        current_id = int(
            message.get(
                "current_track_id",
                -1,
            )
        )

        current = next(
            (
                c
                for c in candles
                if int(
                    c.get(
                        "track_id",
                        -1,
                    )
                )
                == current_id
            ),
            None,
        )

        if current:
            self.current_label.setText(
                "Current: "
                + (
                    "BULLISH"
                    if current.get(
                        "bullish"
                    )
                    else "BEARISH"
                )
            )
            self.current_track.setText(
                f"Track: T{current_id:03d}"
            )
            self.current_state.setText(
                "State: "
                + str(
                    current.get(
                        "track_state",
                        "CURRENT",
                    )
                )
                + " • age "
                + str(
                    current.get(
                        "track_age",
                        0,
                    )
                )
            )
            self.current_conf.setText(
                "Vision: "
                f"{float(current.get('confidence',0))*100:.1f}%"
            )

        clock = message.get(
            "clock",
            {},
        )

        self.current_time.setText(
            "Time: "
            f"{clock.get('start','—')}"
            " → "
            f"{clock.get('end','—')}"
        )

        self.current_remaining.setText(
            "Remaining: "
            f"{clock.get('remaining','—')}s"
        )

        self._update_tracking(
            message
        )

        signal = message.get(
            "signal"
        )

        if (
            signal is not None
            and self.analysis_box.isChecked()
        ):
            self.prediction_label.setText(
                "NEXT "
                f"{signal.get('horizon_seconds',30)}s: "
                f"{signal.get('label','NO TRADE')}"
            )

            self.prediction_probability.setText(
                f"UP {float(signal.get('up_probability',.5))*100:.1f}% | "
                f"DOWN {float(signal.get('down_probability',.5))*100:.1f}%"
            )

            self.prediction_confidence.setText(
                f"Confidence "
                f"{float(signal.get('confidence',0))*100:.1f}% | "
                f"Agreement "
                f"{float(signal.get('agreement',0))*100:.1f}%"
            )

            self.prediction_target.setText(
                "Next window ending "
                + str(
                    clock.get(
                        "end",
                        "—",
                    )
                )
            )

            self._update_audit(
                signal
            )
        else:
            self.prediction_label.setText(
                "VISION SCAN"
            )

        event = message.get(
            "candle_event"
        )

        if event and event.get(
            "closed_candle"
        ):
            closed = event[
                "closed_candle"
            ]

            self.events.append(
                "CANDLE CLOSED "
                f"T{int(closed.get('track_id',-1)):03d} "
                + (
                    "BULL"
                    if closed.get(
                        "bullish"
                    )
                    else "BEAR"
                )
                + " • "
                f"Vision {float(closed.get('confidence',0))*100:.1f}%"
            )

        self._update_overlay(
            message,
            signal,
        )

        self.live_status.setText(
            "LIVE • "
            f"FRAME {self.last_frame_id}"
        )

    # =========================================================
    # TRACKING TABLE
    # =========================================================
    def _update_tracking(
        self,
        message,
    ):
        candles = message.get(
            "candles",
            [],
        )

        current_id = int(
            message.get(
                "current_track_id",
                -1,
            )
        )

        self.tracking_summary.setText(
            "Worker connected • "
            f"Tracked {len(candles)} • "
            f"Stable {message.get('stable_tracks',0)} • "
            f"New {message.get('new_tracks',0)} • "
            f"Recovered {message.get('recovered_tracks',0)} • "
            f"Stability "
            f"{float(message.get('tracking_stability',0))*100:.1f}% • "
            f"Current T{current_id:03d} • "
            f"Restarts {self.worker_restarts}"
        )

        self.table.setRowCount(
            len(candles)
        )

        for row, candle in enumerate(
            candles
        ):
            values = [
                f"T{int(candle.get('track_id',-1)):03d}",
                str(
                    candle.get(
                        "track_state",
                        "",
                    )
                ),
                (
                    "BULL"
                    if candle.get(
                        "bullish"
                    )
                    else "BEAR"
                ),
                f"{float(candle.get('confidence',0))*100:.1f}%",
                str(
                    candle.get(
                        "track_age",
                        0,
                    )
                ),
                f"{float(candle.get('body_size_px',0)):.1f}",
                f"{float(candle.get('upper_wick_px',0)):.1f}",
                f"{float(candle.get('lower_wick_px',0)):.1f}",
                (
                    "YES"
                    if candle.get(
                        "is_current"
                    )
                    else ""
                ),
                str(
                    candle.get(
                        "last_seen_frame",
                        0,
                    )
                ),
            ]

            for column, value in enumerate(
                values
            ):
                item = QTableWidgetItem(
                    value
                )

                if candle.get(
                    "is_current"
                ):
                    item.setBackground(
                        QColor(
                            255,
                            205,
                            60,
                            100,
                        )
                    )

                self.table.setItem(
                    row,
                    column,
                    item,
                )

    # =========================================================
    # AUDIT
    # =========================================================
    def _update_audit(
        self,
        signal,
    ):
        for label in (
            self.layer_labels.values()
        ):
            label.setText(
                "WAITING"
            )

        for component in signal.get(
            "components",
            [],
        ):
            name = component.get(
                "name",
                "",
            )

            if name in self.layer_labels:
                self.layer_labels[
                    name
                ].setText(
                    f"{component.get('direction','N/A')} "
                    f"{float(component.get('probability_up',.5))*100:.1f}%"
                )

        diagnostics = (
            signal.get(
                "diagnostics",
                {},
            )
            or {}
        )

        self.events.append(
            (
                "SIGNAL "
                f"{signal.get('label')} | "
                f"UP {float(signal.get('up_probability',0))*100:.1f}% | "
                f"DOWN {float(signal.get('down_probability',0))*100:.1f}% | "
                f"CONF {float(signal.get('confidence',0))*100:.1f}%"
            )
        )

        self.diagnostics.setPlainText(
            "\n".join([
                "REFERENCE: CURRENT VISIBLE PRICE",
                "",
                f"RSI: {diagnostics.get('rsi')}",
                f"MACD histogram: {diagnostics.get('macd_hist')}",
                f"Stochastic K/D: {diagnostics.get('stoch_k')} / {diagnostics.get('stoch_d')}",
                f"CCI: {diagnostics.get('cci')}",
                f"Williams %R: {diagnostics.get('williams_r')}",
                (
                    "EMA 9/21/50/200: "
                    f"{diagnostics.get('ema9')} / "
                    f"{diagnostics.get('ema21')} / "
                    f"{diagnostics.get('ema50')} / "
                    f"{diagnostics.get('ema200')}"
                ),
                f"ADX: {diagnostics.get('adx')}",
                f"Volatility: {diagnostics.get('volatility_regime')}",
                (
                    "Support/Resistance: "
                    f"{diagnostics.get('support')} / "
                    f"{diagnostics.get('resistance')}"
                ),
                f"VWAP: {diagnostics.get('vwap')}",
                f"Structure: {diagnostics.get('structure')}",
            ])
        )

    # =========================================================
    # OVERLAY
    # =========================================================
    def _update_overlay(
        self,
        message,
        signal,
    ):
        if not self.vision_box.isChecked():
            self.overlay.hide()
            return

        rect = self.last_rect

        if not rect:
            return

        left, top, right, bottom = rect

        boxes = []

        for candle in message.get(
            "candles",
            [],
        ):
            boxes.append(
                (
                    int(
                        candle.get(
                            "body_left",
                            0,
                        )
                    ) - left,
                    int(
                        candle.get(
                            "body_top",
                            0,
                        )
                    ) - top,
                    max(
                        2,
                        int(
                            candle.get(
                                "body_right",
                                0,
                            )
                            - candle.get(
                                "body_left",
                                0,
                            )
                            + 1
                        ),
                    ),
                    max(
                        3,
                        int(
                            candle.get(
                                "body_bottom",
                                0,
                            )
                            - candle.get(
                                "body_top",
                                0,
                            )
                            + 1
                        ),
                    ),
                    float(
                        candle.get(
                            "confidence",
                            0,
                        )
                    ),
                    bool(
                        candle.get(
                            "is_current",
                            False,
                        )
                    ),
                    int(
                        candle.get(
                            "track_id",
                            -1,
                        )
                    ),
                    int(
                        candle.get(
                            "track_age",
                            0,
                        )
                    ),
                    str(
                        candle.get(
                            "track_state",
                            "",
                        )
                    ),
                )
            )

        label = (
            signal.get(
                "label",
                "SCAN",
            )
            if signal
            else "SCAN"
        )

        probability = (
            float(
                signal.get(
                    "up_probability",
                    0.5,
                )
            )
            if signal
            else 0.5
        )

        confidence = (
            float(
                signal.get(
                    "confidence",
                    0.0,
                )
            )
            if signal
            else 0.0
        )

        self.overlay.setGeometry(
            left,
            top,
            max(
                1,
                right - left,
            ),
            max(
                1,
                bottom - top,
            ),
        )

        self.overlay.set_data(
            boxes,
            label,
            probability,
            confidence,
            (
                "LIVE • "
                f"Frame {message.get('frame_id',0)} • "
                f"Tracked {len(boxes)}"
            ),
            current_index=-1,
            tracking_stability=float(
                message.get(
                    "tracking_stability",
                    0,
                )
            ),
            tracked_count=len(boxes),
            frame_id=int(
                message.get(
                    "frame_id",
                    0,
                )
            ),
        )

        self.overlay.show()

    def _set_health(self, name, value):
        label = self.health_labels.get(name)
        if label is not None:
            label.setText(str(value))

    def _update_health(self, message):
        health = message.get("health", {}) or {}
        self._set_health("Worker", "LIVE")
        self._set_health("IPC", "LIVE")
        self._set_health("Capture", f"{health.get('capture_ms','—')} ms")
        self._set_health("Detector", f"{health.get('detect_ms','—')} ms")
        self._set_health("Tracker", f"{health.get('track_ms','—')} ms")
        self._set_health("Analysis", f"{health.get('analysis_ms','—')} ms")
        self._set_health("FPS", health.get("effective_fps","—"))
        self._set_health("Latency", f"{health.get('total_ms','—')} ms")
        self._set_health("Frame", message.get("frame_id","—"))
        self._set_health("Restarts", self.worker_restarts)

    # =========================================================
    # CLOCK / WATCHDOG
    # =========================================================
    def _update_clock(self):
        if not self.running:
            return

        start, end, remaining = (
            self.clock.formatted()
        )

        self.current_time.setText(
            "Time: "
            f"{start} → {end}"
        )

        self.current_remaining.setText(
            "Remaining: "
            f"{remaining}s"
        )

    def _watchdog(self):
        if not self.running:
            return

        now = time.monotonic()

        # No socket or no recent data => restart.
        if (
            self.worker_socket is None
            and self.worker is not None
        ):
            return

        if (
            self.last_message_time
            and now
            - self.last_message_time
            > 8.0
        ):
            self.live_status.setText(
                "WORKER HEARTBEAT LOST — RESTARTING"
            )
            self._restart_worker()

    # =========================================================
    # CONTROLS
    # =========================================================
    def _timeframe_changed(
        self,
        index,
    ):
        self.clock.timeframe_seconds = [
            30,
            60,
            120,
        ][index]

    def _offset_changed(
        self,
        value,
    ):
        self.clock.offset_seconds = value

    def _toggle_boxes(
        self,
        state,
    ):
        if state and self.running:
            self.overlay.show()
        else:
            self.overlay.hide()

    def closeEvent(
        self,
        event,
    ):
        self.stop()

        try:
            if self.server.isListening():
                self.server.close()
        except Exception:
            pass

        event.accept()
