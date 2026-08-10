"""全屏框选截图：选区固定不变，功能条嵌在遮罩内（不随焦点消失）。"""
from __future__ import annotations

from io import BytesIO
from typing import Optional, Tuple

import mss
from PIL import Image
from PySide6.QtCore import QByteArray, QEvent, QEventLoop, QMimeData, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


def _force_solid_bg(widget: QWidget, color: str) -> None:
    """强制不透明背景，避免截图底色透出导致看不清。"""
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    widget.setAutoFillBackground(True)
    pal = widget.palette()
    c = QColor(color)
    pal.setColor(QPalette.ColorRole.Window, c)
    pal.setColor(QPalette.ColorRole.Base, c)
    widget.setPalette(pal)

from app.editor import Canvas, Tool, Worker
from app.settings import AppSettings, save_settings


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


def _pil_to_qimage(img: Image.Image) -> QImage:
    rgba = img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    return QImage(data, rgba.width, rgba.height, QImage.Format.Format_RGBA8888).copy()


def copy_png_to_clipboard(img: Image.Image) -> None:
    """将截图以 PNG 写入剪贴板（兼容多数软件粘贴）。"""
    bio = BytesIO()
    img.convert("RGBA").save(bio, format="PNG")
    png = QByteArray(bio.getvalue())
    mime = QMimeData()
    mime.setData("image/png", png)
    mime.setImageData(_pil_to_qimage(img.convert("RGBA")))
    QApplication.clipboard().setMimeData(mime)


class ShotCanvas(Canvas):
    """选区内画布：支持双击完成、转发 Esc/右键退出。"""

    double_clicked = Signal()
    escape_pressed = Signal()
    right_clicked = Signal()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drawing = False
            self._dragging_text = False
            self.double_clicked.emit()
            e.accept()
            return
        super().mouseDoubleClickEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            e.accept()
            return
        super().keyPressEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit()
            e.accept()
            return
        super().mousePressEvent(e)


class FloatingBar(QWidget):
    """选区外浮动工具条：作为遮罩子控件，避免点击画布后 Tool 窗被系统隐藏。"""

    tool_changed = Signal(object)
    color_clicked = Signal()
    undo_clicked = Signal()
    redo_clicked = Signal()
    copy_clicked = Signal()
    save_clicked = Signal()
    ocr_clicked = Signal()
    translate_clicked = Signal()
    ok_clicked = Signal()
    cancel_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # 不做独立 Tool 窗口，始终挂在全屏遮罩上
        self.setObjectName("floatBar")
        _force_solid_bg(self, "#2d2d30")
        self.setStyleSheet(
            """
            QWidget#floatBar {
                background-color: #2d2d30;
                border: 1px solid #5a5a5a;
                border-radius: 6px;
            }
            QPushButton {
                background-color: #3a3a3e;
                color: #f0f0f0;
                border: 1px solid #4a4a4e;
                border-radius: 4px;
                padding: 6px 8px;
                min-width: 36px;
            }
            QPushButton:hover { background-color: #4a4a50; }
            QPushButton:checked { background-color: #0078d4; border-color: #2890e0; }
            QPushButton#okBtn { color: #4EC9B0; font-weight: 700; background-color: #243028; }
            QPushButton#cancelBtn { color: #F44747; font-weight: 700; background-color: #3a2424; }
            QLabel { color: #888; background: transparent; }
            """
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(3)

        self._tool_btns = []
        tools = [
            ("矩形", Tool.RECT),
            ("椭圆", Tool.ELLIPSE),
            ("箭头", Tool.ARROW),
            ("画笔", Tool.PEN),
            ("文字", Tool.TEXT),
            ("马赛克", Tool.MOSAIC),
        ]
        for name, tool in tools:
            b = QPushButton(name)
            b.setCheckable(True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, t=tool: self._pick_tool(t))
            lay.addWidget(b)
            self._tool_btns.append((b, tool))

        def add_sep():
            line = QLabel("│")
            line.setStyleSheet("color:#555;padding:0 2px;")
            lay.addWidget(line)

        add_sep()
        for text, sig in [
            ("颜色", self.color_clicked),
            ("撤销", self.undo_clicked),
            ("重做", self.redo_clicked),
            ("复制", self.copy_clicked),
            ("保存", self.save_clicked),
        ]:
            b = QPushButton(text)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(sig.emit)
            lay.addWidget(b)

        add_sep()
        b_ocr = QPushButton("提取文字")
        b_ocr.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b_ocr.clicked.connect(self.ocr_clicked.emit)
        lay.addWidget(b_ocr)
        b_tr = QPushButton("对照翻译")
        b_tr.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b_tr.clicked.connect(self.translate_clicked.emit)
        lay.addWidget(b_tr)

        add_sep()
        b_cancel = QPushButton("✕")
        b_cancel.setObjectName("cancelBtn")
        b_cancel.setToolTip("退出截图（软件继续托盘运行）")
        b_cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b_cancel.clicked.connect(self.cancel_clicked.emit)
        lay.addWidget(b_cancel)
        b_ok = QPushButton("✓")
        b_ok.setObjectName("okBtn")
        b_ok.setToolTip("完成：PNG 进剪贴板并退出截图")
        b_ok.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b_ok.clicked.connect(self.ok_clicked.emit)
        lay.addWidget(b_ok)

        self._pick_tool(Tool.RECT)
        self.adjustSize()

    def paintEvent(self, event):
        # 实心底 + 边框，防止截图亮色区域透出
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(QColor("#2d2d30"))
        p.setPen(QPen(QColor("#6a6a6e"), 1))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 6, 6)
        super().paintEvent(event)

    def _pick_tool(self, tool: Tool):
        for b, t in self._tool_btns:
            b.setChecked(t == tool)
        self.tool_changed.emit(tool)


class ResultFloat(QWidget):
    """OCR/翻译结果浮层：挂在遮罩上，不改变截图选区。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("resultFloat")
        _force_solid_bg(self, "#1e1e22")
        self.setStyleSheet(
            """
            QWidget#resultFloat {
                background-color: #1e1e22;
                border: 1px solid #5a5a60;
                border-radius: 6px;
            }
            QLabel { color:#ececec; background: transparent; }
            QTextEdit {
                background-color: #141418;
                color: #f0f0f0;
                border: 1px solid #3a3a40;
                border-radius: 4px;
                selection-background-color: #264f78;
            }
            QPushButton {
                background-color: #333338;
                color: #f0f0f0;
                border: 1px solid #4a4a50;
                border-radius: 4px;
                padding: 4px 10px;
            }
            QPushButton:hover { background-color: #424248; }
            QCheckBox { color:#ddd; background: transparent; spacing: 6px; }
            QCheckBox::indicator { width: 14px; height: 14px; }
            """
        )
        self.setFixedWidth(340)
        self.setMinimumHeight(220)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        head = QHBoxLayout()
        self.lbl_title = QLabel("结果")
        head.addWidget(self.lbl_title)
        head.addStretch(1)
        btn_copy = QPushButton("复制全部")
        btn_copy.clicked.connect(self._copy_all)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.hide)
        head.addWidget(btn_copy)
        head.addWidget(btn_close)
        lay.addLayout(head)

        self.chk_online = QCheckBox("本次联网翻译")
        lay.addWidget(self.chk_online)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        _force_solid_bg(self.text, "#141418")
        lay.addWidget(self.text, 1)

        self.status = QLabel("")
        self.status.setStyleSheet("color:#aaaaaa; background: transparent;")
        lay.addWidget(self.status)
        self._plain = ""

    def paintEvent(self, event):
        # 对照翻译侧栏实心背景，避免被桌面/截图底色干扰
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(QColor("#1e1e22"))
        p.setPen(QPen(QColor("#6a6a70"), 1))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 6, 6)
        super().paintEvent(event)

    def _copy_all(self):
        t = self._plain or self.text.toPlainText()
        if t.strip():
            QApplication.clipboard().setText(t)
            self.status.setText("已复制全部")

    def show_payload(self, title: str, payload: str, plain: str):
        self.lbl_title.setText(title)
        self._plain = plain
        self.text.clear()
        if "\t" in payload and (payload.startswith("src") or "\nsrc\t" in payload):
            for line in payload.splitlines():
                if not line:
                    self.text.append("")
                    continue
                if "\t" not in line:
                    self.text.setTextColor(QColor("#e6e6e6"))
                    self.text.append(line)
                    continue
                kind, content = line.split("\t", 1)
                self.text.setTextColor(QColor("#4EC9B0") if kind == "src" else QColor("#e6e6e6"))
                self.text.append(content)
        else:
            self.text.setTextColor(QColor("#4EC9B0"))
            self.text.setPlainText(payload)
        self.status.setText(f"{title} 完成 · 可划选复制")
        self.show()
        self.raise_()


class CaptureOverlay(QWidget):
    """
    两阶段：
    1) 框选 —— 松手后选区锁定
    2) 编辑 —— 仅在选区内标注；工具条在选区外且不消失
    双击选区 / ✓ ：PNG 进剪贴板并退出截图，托盘继续后台运行
    """

    def __init__(self, screen_img: Image.Image, origin: Tuple[int, int], settings: AppSettings, model_hub=None):
        super().__init__()
        self._img = screen_img
        self._pix = pil_to_qpixmap(screen_img)
        self._origin = origin
        self.settings = settings
        self.model_hub = model_hub

        self._phase = "select"
        self._start: Optional[QPoint] = None
        self._end: Optional[QPoint] = None
        self._sel = QRect()
        self.result: Optional[Image.Image] = None
        self._loop: Optional[QEventLoop] = None
        self._worker: Optional[Worker] = None
        self._closing = False
        # 通过标题条/边框拖动整个截图选区
        self._moving_sel = False
        self._move_last = QPoint()

        self.canvas: Optional[ShotCanvas] = None
        # 关键：作为子控件，避免独立 Tool 窗在点击画布后被系统关掉
        self.bar = FloatingBar(self)
        self.bar.hide()
        self.result_panel = ResultFloat(self)
        self.result_panel.hide()
        self.result_panel.chk_online.setChecked(False)

        self._wire_bar()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(origin[0], origin[1], screen_img.width, screen_img.height)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _wire_bar(self):
        self.bar.tool_changed.connect(self._on_tool)
        self.bar.color_clicked.connect(self._on_color)
        self.bar.undo_clicked.connect(self._undo)
        self.bar.redo_clicked.connect(self._redo)
        self.bar.copy_clicked.connect(self._copy_image)
        self.bar.save_clicked.connect(self._save_image)
        self.bar.ocr_clicked.connect(lambda: self._run_job(False))
        self.bar.translate_clicked.connect(lambda: self._run_job(True))
        self.bar.ok_clicked.connect(self._confirm)
        self.bar.cancel_clicked.connect(self._cancel)

    def _keep_chrome(self):
        """画布操作后确保工具条仍在最前可见。"""
        if self.bar.isHidden():
            return
        self.bar.show()
        self.bar.raise_()
        if self.canvas:
            self.canvas.raise_()
            # 工具条必须在选区外，再抬到 canvas 之上（几何不重叠）
            self.bar.raise_()

    def exec_session(self) -> Optional[Image.Image]:
        self._loop = QEventLoop(self)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self._loop.exec()
        return self.result

    def _finish(self):
        if self._closing:
            return
        self._closing = True
        self.bar.hide()
        self.result_panel.hide()
        if self._loop and self._loop.isRunning():
            self._loop.quit()
        self.hide()
        self.close()

    def _cancel(self):
        """退出截图界面，不写入剪贴板；主程序托盘继续运行。"""
        self.result = None
        self._finish()

    def _confirm(self):
        """PNG 进剪贴板并退出截图区域，软件后台（托盘）继续运行。"""
        if self.canvas is None:
            self._cancel()
            return
        img = self.canvas.compose()
        copy_png_to_clipboard(img)
        self.result = img
        self._finish()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.drawPixmap(0, 0, self._pix)
        p.fillRect(self.rect(), QColor(0, 0, 0, 90))

        r = self._current_rect()
        if r.isValid() and r.width() >= 2 and r.height() >= 2:
            if self._phase == "select" or self.canvas is None:
                p.drawPixmap(r, self._pix, r)
            p.setPen(QPen(QColor(0, 200, 80), 2))
            p.drawRect(r.adjusted(0, 0, -1, -1))
            tip = f"{r.width()} × {r.height()}"
            tip_r = self._tip_rect() if self._phase == "edit" else QRect(r.left(), max(0, r.top() - 26), 120, 26)
            p.fillRect(tip_r, QColor(0, 0, 0, 200))
            p.setPen(QColor("white"))
            p.drawText(tip_r.left() + 6, tip_r.top() + 17, tip)

        # 底部提示条用不透明底，避免亮色桌面干扰阅读
        if self._phase in ("select", "edit"):
            p.fillRect(0, self.height() - 30, self.width(), 30, QColor(30, 30, 34, 235))
            p.setPen(QColor(240, 240, 240))
            if self._phase == "select":
                tip = "拖拽选择 · 松手后选区外用工具 · 双击选区=PNG进剪贴板并退出 · Esc取消"
            else:
                tip = "拖尺寸条/绿色边框可移动截图 · 点住文字可拖动 · 双击=PNG进剪贴板并退出 · Esc取消"
            p.drawText(16, self.height() - 10, tip)

    def _current_rect(self) -> QRect:
        if self._phase == "edit" and self._sel.isValid():
            return QRect(self._sel)
        if self._start and self._end:
            return QRect(self._start, self._end).normalized()
        return QRect()

    def _tip_rect(self) -> QRect:
        """选区上方尺寸条热区（加宽便于拖动）。"""
        r = self._sel
        if not r.isValid():
            return QRect()
        return QRect(r.left(), max(0, r.top() - 26), max(120, min(r.width(), 200)), 26)

    def _border_hit(self, pos: QPoint) -> bool:
        """点在选区标题条或绿色边框外围 → 可拖动整块截图。"""
        if not self._sel.isValid():
            return False
        if self._tip_rect().contains(pos):
            return True
        # 绿色边框外围一圈（不进入选区内部，避免与标注冲突）
        outer = self._sel.adjusted(-14, -14, 14, 14)
        return outer.contains(pos) and not self._sel.contains(pos)

    def _nudge_sel(self, dx: int, dy: int):
        """平移选区与画布，内容不变，工具条跟随。"""
        if not self._sel.isValid() or not self.canvas:
            return
        nr = self._sel.translated(dx, dy)
        # 限制在屏幕内
        if nr.left() < 0:
            nr.moveLeft(0)
        if nr.top() < 0:
            nr.moveTop(0)
        if nr.right() > self.width() - 1:
            nr.moveRight(self.width() - 1)
        if nr.bottom() > self.height() - 1:
            nr.moveBottom(self.height() - 1)
        self._sel = nr
        self.canvas.setGeometry(self._sel)
        self._place_bar()
        if not self.result_panel.isHidden():
            self._place_result()
        self.update()
        self._keep_chrome()

    def mousePressEvent(self, e):
        if self._phase == "edit":
            if e.button() == Qt.MouseButton.RightButton:
                self._cancel()
                return
            if e.button() == Qt.MouseButton.LeftButton:
                pos = e.position().toPoint()
                if self._border_hit(pos):
                    self._moving_sel = True
                    self._move_last = pos
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                    return
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self._start = e.position().toPoint()
            self._end = self._start
            self.update()
        elif e.button() == Qt.MouseButton.RightButton:
            self._cancel()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._phase == "edit":
            if self._moving_sel:
                dx = pos.x() - self._move_last.x()
                dy = pos.y() - self._move_last.y()
                self._move_last = pos
                self._nudge_sel(dx, dy)
                return
            # 悬停边框提示可拖动
            if self._border_hit(pos):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        if self._start is not None:
            self._end = pos
            self.update()

    def mouseReleaseEvent(self, e):
        if self._phase == "edit":
            if self._moving_sel and e.button() == Qt.MouseButton.LeftButton:
                self._moving_sel = False
                self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        if e.button() == Qt.MouseButton.LeftButton and self._start and self._end:
            r = QRect(self._start, self._end).normalized()
            if r.width() >= 5 and r.height() >= 5:
                self._enter_edit(r)
            else:
                self._start = self._end = None
                self.update()

    def mouseDoubleClickEvent(self, e):
        # 选区外双击无效；选区内由 ShotCanvas 处理
        if self._phase == "edit" and e.button() == Qt.MouseButton.LeftButton:
            if self._sel.contains(e.position().toPoint()):
                self._confirm()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._cancel()
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._phase == "edit":
            self._confirm()

    def _enter_edit(self, r: QRect):
        """锁定选区；工具条作为子控件放在选区外。"""
        self._phase = "edit"
        self._sel = QRect(r)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        crop = self._img.crop((r.left(), r.top(), r.right() + 1, r.bottom() + 1))
        self.canvas = ShotCanvas(crop)
        self.canvas.setParent(self)
        self.canvas.setGeometry(r)
        self.canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.canvas.double_clicked.connect(self._confirm)
        self.canvas.escape_pressed.connect(self._cancel)
        self.canvas.right_clicked.connect(self._cancel)
        self.canvas.installEventFilter(self)
        self.canvas.show()

        self._place_bar()
        self.bar.show()
        self._keep_chrome()
        self.canvas.setFocus()
        self.update()

    def eventFilter(self, obj, event):
        # 画布获得焦点/鼠标后，强制工具条保持显示
        if obj is self.canvas and event.type() in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.FocusIn,
        ):
            self._keep_chrome()
        return super().eventFilter(obj, event)

    def _place_bar(self):
        self.bar.adjustSize()
        bw, bh = self.bar.width(), self.bar.height()
        gap = 8
        x = self._sel.left()
        y = self._sel.bottom() + gap
        if x + bw > self.width() - 4:
            x = max(4, self.width() - bw - 4)
        if y + bh > self.height() - 4:
            y = self._sel.top() - gap - bh
        if y < 4:
            y = 4
        self.bar.move(x, y)

    def _place_result(self):
        self.result_panel.adjustSize()
        rh = min(420, max(260, self._sel.height()))
        self.result_panel.setFixedHeight(rh)
        rw = self.result_panel.width()
        gap = 8
        x = self._sel.right() + gap
        y = self._sel.top()
        if x + rw > self.width() - 4:
            x = max(4, self._sel.left())
            y = self.bar.y() + self.bar.height() + gap
        if y + self.result_panel.height() > self.height() - 4:
            y = max(4, self.height() - self.result_panel.height() - 4)
        self.result_panel.move(x, y)

    def _undo(self):
        if self.canvas:
            self.canvas.undo()
        self._keep_chrome()

    def _redo(self):
        if self.canvas:
            self.canvas.redo()
        self._keep_chrome()

    def _on_tool(self, tool: Tool):
        if self.canvas:
            self.canvas.tool = tool
            if tool == Tool.TEXT:
                self.canvas.setCursor(Qt.CursorShape.IBeamCursor)
            else:
                self.canvas.setCursor(Qt.CursorShape.CrossCursor)
        self._keep_chrome()
    def _on_color(self):
        if not self.canvas:
            return
        c = QColorDialog.getColor(QColor(*self.canvas.color[:3]), self, "标注颜色")
        if c.isValid():
            self.canvas.color = (c.red(), c.green(), c.blue(), 255)
        self._keep_chrome()

    def _copy_image(self):
        if not self.canvas:
            return
        copy_png_to_clipboard(self.canvas.compose())
        self.result_panel.status.setText("PNG 已复制到剪贴板")
        self._keep_chrome()

    def _save_image(self):
        if not self.canvas:
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存截图", "截图.png", "PNG (*.png);;JPEG (*.jpg)")
        if path:
            self.canvas.compose().save(path)
            self.result_panel.status.setText("已保存：" + path)
        self._keep_chrome()

    def _run_job(self, do_translate: bool):
        if not self.canvas:
            return
        if self._worker and self._worker.isRunning():
            return
        use_online = self.result_panel.chk_online.isChecked()
        self.settings.use_online = use_online
        save_settings(self.settings)

        self._place_result()
        self.result_panel.show()
        self.result_panel.raise_()
        self.bar.raise_()
        self.result_panel.status.setText("处理中…")
        self.result_panel.lbl_title.setText("对照翻译" if do_translate else "提取文字")

        self._worker = Worker(self.canvas.compose(), do_translate, use_online)
        self._worker.status.connect(self.result_panel.status.setText)
        self._worker.finished_ok.connect(self._on_job_done)
        self._worker.failed.connect(lambda e: QMessageBox.warning(self, "失败", e))
        self._worker.start()

    def _on_job_done(self, title: str, payload: str, plain: str):
        self.result_panel.show_payload(title, payload, plain)
        self._place_result()
        self._keep_chrome()


def select_region(settings: Optional[AppSettings] = None, model_hub=None) -> Optional[Image.Image]:
    """框选编辑；确认/双击后返回图片。退出后主程序仍托盘后台运行。"""
    img, origin = grab_virtual_screen()
    if settings is None:
        settings = AppSettings()
    overlay = CaptureOverlay(img, origin, settings, model_hub=model_hub)
    return overlay.exec_session()
