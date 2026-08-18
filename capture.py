from __future__ import annotations

from typing import Optional, Tuple

import mss
import numpy as np
import win32gui


def find_window(
    title_fragment: str,
) -> Optional[int]:
    target = (
        title_fragment
        .lower()
        .strip()
    )
    found = []

    def callback(hwnd, _):
        try:
            if (
                win32gui.IsWindowVisible(hwnd)
                and target in (
                    win32gui
                    .GetWindowText(hwnd)
                    .lower()
                )
            ):
                found.append(hwnd)
        except Exception:
            pass
        return True

    win32gui.EnumWindows(
        callback,
        None,
    )

    if not found:
        return None

    found.sort(
        key=lambda hwnd: (
            (
                win32gui.GetWindowRect(hwnd)[2]
                - win32gui.GetWindowRect(hwnd)[0]
            )
            * (
                win32gui.GetWindowRect(hwnd)[3]
                - win32gui.GetWindowRect(hwnd)[1]
            )
        ),
        reverse=True,
    )

    return found[0]


class WindowCapture:
    """
    Small, restartable screen-capture wrapper.

    A fresh MSS object can be created after a failed capture. This avoids
    keeping a broken native capture handle alive across subsequent frames.
    """

    def __init__(self):
        self.sct = None
        self._open()

    def _open(self):
        if self.sct is not None:
            try:
                self.sct.close()
            except Exception:
                pass
        self.sct = mss.mss()

    def get_window_rect(
        self,
        hwnd: int,
    ) -> Tuple[int, int, int, int]:
        return win32gui.GetWindowRect(hwnd)

    def capture(
        self,
        hwnd: int,
    ):
        try:
            left, top, right, bottom = (
                self.get_window_rect(hwnd)
            )

            width = max(
                1,
                right - left,
            )
            height = max(
                1,
                bottom - top,
            )

            shot = self.sct.grab(
                {
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
                }
            )

            frame = (
                np.asarray(shot)
               [:, :, :3]
                [:, :, ::-1]
                .copy()
            )

            return frame, (
                left,
                top,
                right,
                bottom,
            )

        except Exception:
            self._open()
            raise

    def capture_window(
        self,
        hwnd: int,
    ):
        return self.capture(hwnd)
