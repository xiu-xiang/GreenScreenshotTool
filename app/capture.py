"""全屏框选截图（类似微信）。"""
from __future__ import annotations

from typing import Optional, Tuple

import mss
from PIL import Image
from PySide6.QtCore import QEventLoop, QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QWidget


def grab_virtual_screen() -> Tuple[Image.Image, Tuple[int, int]]:
    with mss.mss() as sct:
        mon = sct.monitors[0]
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        return img, (mon["left"], mon["top"])


def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    rgba = img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimg = QImage(data, rgba.width, rgba.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


class SelectionOverlay(QWidget):
    def __init__(self, screen_img: Image.Image, origin: Tuple[int, int]):
        super().__init__()
        self._img = screen_img
        self._pix = pil_to_qpixmap(screen_img)
        self._start: Optional[QPoint] = None
        self._end: Optional[QPoint] = None
        self.result: Optional[Image.Image] = None
        self._loop: Optional[QEventLoop] = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(origin[0], origin[1], screen_img.width, screen_img.height)

    def exec_select(self) -> Optional[Image.Image]:
        self._loop = QEventLoop(self)
        self.show()
        self.raise_()
        self.activateWindow()
        self._loop.exec()
        return self.result

    def _finish(self):
        if self._loop:
            self._loop.quit()
        self.close()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.drawPixmap(0, 0, self._pix)
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))
        if self._start and self._end:
            r = QRect(self._start, self._end).normalized()
            p.drawPixmap(r, self._pix, r)
            p.setPen(QPen(QColor(0, 174, 255), 2))
            p.drawRect(r.adjusted(0, 0, -1, -1))
            tip = f"{r.width()} x {r.height()}"
            p.fillRect(r.left(), max(0, r.top() - 22), 90, 20, QColor(0, 0, 0, 180))
            p.setPen(QColor("white"))
            p.drawText(r.left() + 6, max(14, r.top() - 6), tip)
        p.setPen(QColor("white"))
        p.drawText(20, self.height() - 24, "拖拽选择区域 | Esc/右键 取消 | 松手完成")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._start = e.position().toPoint()
            self._end = self._start
            self.update()
        elif e.button() == Qt.MouseButton.RightButton:
            self.result = None
            self._finish()

    def mouseMoveEvent(self, e):
        if self._start is not None:
            self._end = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._start and self._end:
            r = QRect(self._start, self._end).normalized()
            if r.width() >= 5 and r.height() >= 5:
                self.result = self._img.crop((r.left(), r.top(), r.right() + 1, r.bottom() + 1))
                self._finish()
            else:
                self._start = self._end = None
                self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.result = None
            self._finish()


def select_region() -> Optional[Image.Image]:
    img, origin = grab_virtual_screen()
    overlay = SelectionOverlay(img, origin)
    return overlay.exec_select()
