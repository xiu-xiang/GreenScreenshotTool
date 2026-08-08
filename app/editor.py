"""截图编辑器：标注 + 右侧 OCR/对照翻译结果（同窗显示）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QPoint, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from app import ocr_service, translate_service
from app.settings import AppSettings, save_settings


def _pil_to_qimage(img: Image.Image) -> QImage:
    rgba = img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    return QImage(data, rgba.width, rgba.height, QImage.Format.Format_RGBA8888).copy()


def _pil_to_pixmap(img: Image.Image) -> QPixmap:
    return QPixmap.fromImage(_pil_to_qimage(img))


class Tool(Enum):
    RECT = auto()
    ELLIPSE = auto()
    ARROW = auto()
    PEN = auto()
    TEXT = auto()
    MOSAIC = auto()


@dataclass
class Shape:
    tool: Tool
    color: tuple
    width: int
    p1: tuple
    p2: tuple
    text: str = ""
    points: List[tuple] = field(default_factory=list)


class Worker(QThread):
    """后台 OCR / 翻译，结果信号回传主界面。"""

    status = Signal(str)
    finished_ok = Signal(str, str, str)  # title, display_html_or_text, plain
    failed = Signal(str)

    def __init__(self, image: Image.Image, do_translate: bool, use_online: bool):
        super().__init__()
        self.image = image
        self.do_translate = do_translate
        self.use_online = use_online

    def run(self):
        try:
            self.status.emit("正在 OCR 识别（离线 RapidOCR）...")
            ocr = ocr_service.extract_text(self.image)
            if not self.do_translate:
                plain = ocr.full_text
                disp = "\n".join(ocr.lines)
                self.finished_ok.emit(
                    "提取文字",
                    disp,
                    plain,
                )
                return

            self.status.emit("识别完成，开始对照翻译...")
            lines = translate_service.translate_contrast(
                ocr.lines,
                use_online=self.use_online,
                progress=lambda s: self.status.emit(s),
            )
            # 对照显示：原文绿 / 译文白（用纯文本+前缀，侧栏用样式着色）
            chunks = []
            for x in lines:
                chunks.append(("src", "// " + x.source))
                chunks.append(("dst", x.translation))
                chunks.append(("dst", ""))
            plain = translate_service.format_contrast(lines)
            # 用特殊分隔传回
            payload = "\n".join(f"{k}\t{v}" for k, v in chunks)
            title = "对照翻译（联网）" if self.use_online else "对照翻译（离线）"
            self.finished_ok.emit(title, payload, plain)
        except Exception as ex:
            self.failed.emit(str(ex))


class Canvas(QWidget):
    def __init__(self, image: Image.Image):
        super().__init__()
        self.base = image.convert("RGBA")
        self.shapes: List[Shape] = []
        self.redo_stack: List[Shape] = []
        self.tool = Tool.RECT
        self.color = (255, 60, 60, 255)
        self.pen_w = 3
        self._drawing = False
        self._start = QPoint()
        self._cur = QPoint()
        self._pen_pts: List[tuple] = []
        self.setMinimumSize(self.base.width, self.base.height)
        self.setMouseTracking(True)

    def sizeHint(self):
        from PySide6.QtCore import QSize

        return QSize(self.base.width, self.base.height)

    def paintEvent(self, _e):
        pix = _pil_to_pixmap(self._compose_preview())
        p = QPainter(self)
        p.drawPixmap(0, 0, pix)

    def _compose_preview(self) -> Image.Image:
        img = self.base.copy()
        draw = ImageDraw.Draw(img)
        for s in self.shapes:
            self._draw_shape(draw, img, s)
        if self._drawing:
            tmp = Shape(
                self.tool,
                self.color,
                self.pen_w,
                (self._start.x(), self._start.y()),
                (self._cur.x(), self._cur.y()),
                points=list(self._pen_pts),
            )
            self._draw_shape(draw, img, tmp)
        return img

    def compose(self) -> Image.Image:
        img = self.base.copy()
        draw = ImageDraw.Draw(img)
        for s in self.shapes:
            self._draw_shape(draw, img, s)
        return img.convert("RGB")

    def _draw_shape(self, draw: ImageDraw.ImageDraw, img: Image.Image, s: Shape):
        c = s.color
        w = s.width
        x1, y1 = s.p1
        x2, y2 = s.p2
        box = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
        if s.tool == Tool.RECT:
            draw.rectangle(box, outline=c, width=w)
        elif s.tool == Tool.ELLIPSE:
            draw.ellipse(box, outline=c, width=w)
        elif s.tool == Tool.ARROW:
            draw.line([s.p1, s.p2], fill=c, width=w)
            self._arrow_head(draw, s.p1, s.p2, c, w)
        elif s.tool == Tool.PEN:
            if len(s.points) >= 2:
                draw.line(s.points, fill=c, width=w, joint="curve")
        elif s.tool == Tool.TEXT and s.text:
            try:
                font = ImageFont.truetype("msyh.ttc", 18)
            except Exception:
                font = ImageFont.load_default()
            draw.text(s.p1, s.text, fill=c, font=font)
        elif s.tool == Tool.MOSAIC:
            self._mosaic(img, box)

    def _arrow_head(self, draw, p1, p2, c, w):
        import math

        ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
        L = 14
        a = math.pi / 7
        p_a = (p2[0] - L * math.cos(ang - a), p2[1] - L * math.sin(ang - a))
        p_b = (p2[0] - L * math.cos(ang + a), p2[1] - L * math.sin(ang + a))
        draw.polygon([p2, p_a, p_b], fill=c)

    def _mosaic(self, img: Image.Image, box):
        x1, y1, x2, y2 = [int(v) for v in box]
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(img.width, x2)
        y2 = min(img.height, y2)
        if x2 - x1 < 4 or y2 - y1 < 4:
            return
        region = img.crop((x1, y1, x2, y2))
        small = region.resize((max(1, (x2 - x1) // 8), max(1, (y2 - y1) // 8)), Image.BILINEAR)
        region = small.resize((x2 - x1, y2 - y1), Image.NEAREST)
        img.paste(region, (x1, y1))

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self.tool == Tool.TEXT:
            text, ok = QInputDialog.getText(self, "输入文字", "文字内容：")
            if ok and text.strip():
                pt = (e.position().toPoint().x(), e.position().toPoint().y())
                self.shapes.append(Shape(Tool.TEXT, self.color, self.pen_w, pt, pt, text=text.strip()))
                self.redo_stack.clear()
                self.update()
            return
        self._drawing = True
        self._start = e.position().toPoint()
        self._cur = self._start
        self._pen_pts = [(self._start.x(), self._start.y())]

    def mouseMoveEvent(self, e):
        if not self._drawing:
            return
        self._cur = e.position().toPoint()
        if self.tool == Tool.PEN:
            self._pen_pts.append((self._cur.x(), self._cur.y()))
        self.update()

    def mouseReleaseEvent(self, e):
        if not self._drawing:
            return
        self._drawing = False
        self._cur = e.position().toPoint()
        shape = Shape(
            self.tool,
            self.color,
            self.pen_w,
            (self._start.x(), self._start.y()),
            (self._cur.x(), self._cur.y()),
            points=list(self._pen_pts),
        )
        if self.tool != Tool.PEN and abs(shape.p1[0] - shape.p2[0]) < 3 and abs(shape.p1[1] - shape.p2[1]) < 3:
            return
        self.shapes.append(shape)
        self.redo_stack.clear()
        self.update()

    def undo(self):
        if self.shapes:
            self.redo_stack.append(self.shapes.pop())
            self.update()

    def redo(self):
        if self.redo_stack:
            self.shapes.append(self.redo_stack.pop())
            self.update()


class EditorWindow(QMainWindow):
    def __init__(self, image: Image.Image, settings: AppSettings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle("截图编辑 - 绿色便携版（默认离线）")
        self.resize(settings.window_width, settings.window_height)

        self.canvas = Canvas(image)
        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setStyleSheet(
            "QTextEdit{background:#1e1e1e;color:#e6e6e6;font-family:Consolas,'Cascadia Mono';font-size:12px;}"
        )
        self.result.setPlaceholderText("提取/翻译结果将显示在这里，可自由划选复制")

        self.status = QLabel("就绪 · 本次启动：离线本机模式")
        self.chk_online = QCheckBox("本次使用联网翻译（默认关闭/离线）")
        self.chk_online.setChecked(False)  # 启动默认离线
        self.chk_online.setToolTip("仅影响本次运行；下次启动仍默认离线")
        self.chk_online.toggled.connect(self._on_online_toggled)

        right = QWidget()
        rv = QVBoxLayout(right)
        head = QHBoxLayout()
        self.lbl_title = QLabel("结果")
        head.addWidget(self.lbl_title)
        head.addStretch(1)
        btn_copy = QPushButton("复制选中")
        btn_copy.clicked.connect(self.copy_selected)
        btn_all = QPushButton("复制全部")
        btn_all.clicked.connect(self.copy_all)
        head.addWidget(btn_copy)
        head.addWidget(btn_all)
        rv.addLayout(head)
        rv.addWidget(self.chk_online)
        rv.addWidget(self.result, 1)
        rv.addWidget(self.status)

        split = QSplitter()
        host = QWidget()
        hl = QVBoxLayout(host)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(self.canvas)
        split.addWidget(host)
        split.addWidget(right)
        split.setSizes([700, 360])
        self.setCentralWidget(split)

        self._plain = ""
        self._worker: Optional[Worker] = None
        self._build_toolbar()

    def _on_online_toggled(self, checked: bool):
        self.settings.use_online = bool(checked)
        save_settings(self.settings)
        mode = "联网" if self.settings.use_online else "离线本机"
        self.status.setText(f"已切换：{mode}（下次启动仍默认离线）")

    def _build_toolbar(self):
        tb = QToolBar()
        self.addToolBar(tb)

        def add_tool(name, tool):
            act = QAction(name, self)
            act.triggered.connect(lambda: setattr(self.canvas, "tool", tool) or self.canvas.setCursor(
                Qt.CursorShape.IBeamCursor if tool == Tool.TEXT else Qt.CursorShape.CrossCursor
            ))
            tb.addAction(act)

        add_tool("矩形", Tool.RECT)
        add_tool("椭圆", Tool.ELLIPSE)
        add_tool("箭头", Tool.ARROW)
        add_tool("画笔", Tool.PEN)
        add_tool("文字", Tool.TEXT)
        add_tool("马赛克", Tool.MOSAIC)
        tb.addSeparator()
        act_color = QAction("颜色", self)
        act_color.triggered.connect(self.pick_color)
        tb.addAction(act_color)
        tb.addSeparator()
        for name, slot in [
            ("撤销", self.canvas.undo),
            ("重做", self.canvas.redo),
            ("复制图片", self.copy_image),
            ("保存", self.save_image),
            ("提取文字", lambda: self.run_job(False)),
            ("对照翻译", lambda: self.run_job(True)),
        ]:
            a = QAction(name, self)
            a.triggered.connect(slot)
            tb.addAction(a)

    def pick_color(self):
        c = QColorDialog.getColor(QColor(*self.canvas.color[:3]), self)
        if c.isValid():
            self.canvas.color = (c.red(), c.green(), c.blue(), 255)

    def copy_image(self):
        img = self.canvas.compose()
        QApplication.clipboard().setImage(_pil_to_qimage(img.convert("RGBA")))
        self.status.setText("图片已复制")

    def save_image(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存截图", "截图.png", "PNG (*.png);;JPEG (*.jpg)")
        if not path:
            return
        self.canvas.compose().save(path)
        self.status.setText("已保存：" + path)

    def run_job(self, do_translate: bool):
        if self._worker and self._worker.isRunning():
            return
        # 右侧展开显示
        img = self.canvas.compose()
        use_online = self.chk_online.isChecked()
        self.settings.use_online = use_online
        self._worker = Worker(img, do_translate, use_online)
        self._worker.status.connect(self.status.setText)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(lambda e: QMessageBox.warning(self, "失败", e))
        self._worker.start()

    def _on_done(self, title: str, payload: str, plain: str):
        self.lbl_title.setText(title)
        self._plain = plain
        self.result.clear()
        # 对照格式：src\t行 / dst\t行
        if "\t" in payload and payload.startswith("src\t") or "\nsrc\t" in payload or payload.startswith("src"):
            for line in payload.splitlines():
                if not line:
                    self.result.append("")
                    continue
                if "\t" not in line:
                    self.result.setTextColor(QColor("#e6e6e6"))
                    self.result.append(line)
                    continue
                kind, text = line.split("\t", 1)
                if kind == "src":
                    self.result.setTextColor(QColor("#4EC9B0"))
                else:
                    self.result.setTextColor(QColor("#e6e6e6"))
                self.result.append(text)
        else:
            self.result.setTextColor(QColor("#4EC9B0"))
            self.result.setPlainText(payload)
        self.status.setText(f"{title} 完成 · 可划选复制")

    def copy_selected(self):
        cursor = self.result.textCursor()
        text = cursor.selectedText().replace("\u2029", "\n")
        if not text.strip():
            self.status.setText("请先选中文本")
            return
        QApplication.clipboard().setText(text)
        self.status.setText(f"已复制选中（{len(text)} 字）")

    def copy_all(self):
        text = self._plain or self.result.toPlainText()
        if not text.strip():
            return
        QApplication.clipboard().setText(text)
        self.status.setText("已复制全部")
