from __future__ import annotations
from typing import Iterable, Tuple
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.boxes = []
        self.signal_text = "NO TRADE"
        self.signal_probability = 50.0
        self.confidence = 0.0
        self.status = "WAITING"
        self.current_index = -1
        self.tracking_stability = 0.0
        self.tracked_count = 0
        self.frame_id = 0

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_data(
        self,
        boxes: Iterable[Tuple],
        label,
        probability,
        confidence,
        status,
        current_index=-1,
        tracking_stability=0.0,
        tracked_count=0,
        frame_id=0,
    ):
        self.boxes = list(boxes)
        self.signal_text = label
        self.signal_probability = probability
        self.confidence = confidence
        self.status = status
        self.current_index = current_index
        self.tracking_stability = tracking_stability
        self.tracked_count = tracked_count
        self.frame_id = frame_id
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        for x, y, w, h, conf, is_current, track_id, age, state in self.boxes:
            if is_current:
                color, width = QColor(255, 205, 40, 245), 3
            elif age >= 3:
                color, width = QColor(0, 220, 150, 195), 2
            else:
                color, width = QColor(70, 180, 255, 190), 2

            pen = QPen(color)
            pen.setWidth(width)
            painter.setPen(pen)
            painter.drawRect(x, y, w, h)

            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.setPen(QColor(255, 255, 255, 235))
            painter.drawText(
                x,
                max(14, y - 3),
                f"T{track_id:03d} {conf * 100:.0f}%",
            )

            if is_current:
                painter.setPen(QColor(255, 210, 50, 250))
                painter.drawText(x, y + h + 13, "CURRENT")

        width = min(560, max(360, self.width() - 20))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(4, 15, 24, 182))
        painter.drawRoundedRect(10, 10, width, 132, 12, 12)

        painter.setPen(QColor(255, 255, 255, 245))
        painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
        painter.drawText(24, 31, "QUOTEX VISION AI • CANDLE TRACKER")

        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(
            24,
            50,
            f"TRACKED {self.tracked_count} • STABILITY {self.tracking_stability * 100:.0f}% • FRAME {self.frame_id}",
        )

        color = QColor(255, 200, 40, 245)
        if self.signal_text == "UP":
            color = QColor(30, 230, 145, 250)
        elif self.signal_text == "DOWN":
            color = QColor(255, 90, 105, 250)

        painter.setPen(color)
        painter.setFont(QFont("Segoe UI", 18, QFont.Bold))
        painter.drawText(24, 78, f"NEXT: {self.signal_text}")

        painter.setPen(QColor(255, 255, 255, 230))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(190, 74, f"UP {self.signal_probability * 100:.1f}%")
        painter.drawText(190, 92, f"CONF {self.confidence * 100:.0f}%")
        painter.drawText(24, 118, self.status[:76])
