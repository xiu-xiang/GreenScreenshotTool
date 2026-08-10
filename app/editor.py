"""截图编辑器：标注 + 右侧 OCR/对照翻译结果（同窗显示）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QPoint, QRect, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QImage, QPainter, QPen, QPixmap
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
    QScrollArea,
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

            if self.use_online:
                self.status.emit("识别完成，开始联网对照翻译…")
            elif translate_service.is_model_ready():
                self.status.emit("识别完成，模型已就绪，开始对照翻译…")
            else:
                self.status.emit("识别完成，正在加载离线翻译模型…")
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
        # 文字拖动
        self._dragging_text = False
        self._drag_text_i = -1
        self._drag_text_off = (0, 0)
        # 画布尺寸严格等于截图，避免周围留出空白背景
        w, h = self.base.size
        self.setFixedSize(w, h)
        self.setMouseTracking(True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")

    def sizeHint(self):
        from PySide6.QtCore import QSize

        return QSize(self.base.width, self.base.height)

    def paintEvent(self, _e):
        # 只绘制截图像素，不填充控件背景
        pix = _pil_to_pixmap(self._compose_preview())
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawPixmap(0, 0, pix)
        # 拖动中的文字加虚线框提示
        if self._dragging_text and 0 <= self._drag_text_i < len(self.shapes):
            s = self.shapes[self._drag_text_i]
            br = self._text_bbox(s)
            p.setPen(QPen(QColor(0, 174, 255), 1, Qt.PenStyle.DashLine))
            p.drawRect(br)

    def _text_font(self):
        try:
            return ImageFont.truetype("msyh.ttc", 18)
        except Exception:
            return ImageFont.load_default()

    def _text_bbox(self, s: Shape) -> QRect:
        """估算文字点击/拖动热区。"""
        font = self._text_font()
        try:
            bbox = font.getbbox(s.text or " ")
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            tw, th = max(12, len(s.text or "") * 10), 20
        x, y = int(s.p1[0]), int(s.p1[1])
        return QRect(x - 2, y - 2, max(tw + 8, 16), max(th + 8, 18))

    def _hit_text_index(self, pos: QPoint) -> int:
        for i in range(len(self.shapes) - 1, -1, -1):
            s = self.shapes[i]
            if s.tool == Tool.TEXT and s.text and self._text_bbox(s).contains(pos):
                return i
        return -1

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
            draw.text(s.p1, s.text, fill=c, font=self._text_font())
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
        if e.button() == Qt.MouseButton.RightButton:
            # 子类可覆盖；基类忽略
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = e.position().toPoint()

        # 优先：点中已有文字 → 拖动文字
        hit = self._hit_text_index(pos)
        if hit >= 0:
            self._dragging_text = True
            self._drag_text_i = hit
            s = self.shapes[hit]
            self._drag_text_off = (pos.x() - int(s.p1[0]), pos.y() - int(s.p1[1]))
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            self.update()
            return

        if self.tool == Tool.TEXT:
            text, ok = QInputDialog.getText(self, "输入文字", "文字内容：")
            if ok and text.strip():
                pt = (pos.x(), pos.y())
                self.shapes.append(Shape(Tool.TEXT, self.color, self.pen_w, pt, pt, text=text.strip()))
                self.redo_stack.clear()
                self.update()
            return

        self._drawing = True
        self._start = pos
        self._cur = self._start
        self._pen_pts = [(self._start.x(), self._start.y())]

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()

        if self._dragging_text and 0 <= self._drag_text_i < len(self.shapes):
            s = self.shapes[self._drag_text_i]
            nx = pos.x() - self._drag_text_off[0]
            ny = pos.y() - self._drag_text_off[1]
            # 限制在画布内
            br = self._text_bbox(s)
            nx = max(0, min(nx, self.width() - max(8, br.width())))
            ny = max(0, min(ny, self.height() - max(8, br.height())))
            s.p1 = (nx, ny)
            s.p2 = (nx, ny)
            self.update()
            return

        # 悬停文字时显示可拖动光标
        if not self._drawing and self._hit_text_index(pos) >= 0:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        elif self.tool == Tool.TEXT:
            self.setCursor(Qt.CursorShape.IBeamCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

        if not self._drawing:
            return
        self._cur = pos
        if self.tool == Tool.PEN:
            self._pen_pts.append((self._cur.x(), self._cur.y()))
        self.update()

    def mouseReleaseEvent(self, e):
        if self._dragging_text:
            self._dragging_text = False
            self._drag_text_i = -1
            self.update()
            return
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
    def __init__(self, image: Image.Image, settings: AppSettings, model_hub=None):
        super().__init__()
        self.settings = settings
        self.model_hub = model_hub
        self.setWindowTitle("截图编辑")
        # 主页面以截图为唯一视觉主体，去掉多余灰色背景感
        self.setStyleSheet(
            """
            QMainWindow { background: #111111; }
            QToolBar { background: #1a1a1a; border: none; spacing: 4px; padding: 4px; }
            QToolBar QToolButton { color: #e8e8e8; padding: 4px 8px; }
            QSplitter::handle { background: #2a2a2a; width: 2px; }
            QScrollArea { background: #111111; border: none; }
            QLabel#shotHint { color: #888888; font-size: 11px; }
            """
        )

        self.canvas = Canvas(image)

        # 左侧：只承载截图（可滚动，无额外装饰背景）
        self.shot_host = QWidget()
        self.shot_host.setStyleSheet("background:#111111;")
        shot_layout = QVBoxLayout(self.shot_host)
        shot_layout.setContentsMargins(0, 0, 0, 0)
        shot_layout.setSpacing(0)
        shot_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        shot_layout.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setWidget(self.shot_host)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setStyleSheet(
            "QTextEdit{background:#161616;color:#e6e6e6;border:none;"
            "font-family:Consolas,'Cascadia Mono';font-size:12px;}"
        )
        self.result.setPlaceholderText("提取/翻译结果将显示在这里，可自由划选复制")

        self.status = QLabel("就绪 · 离线本机")
        self.status.setStyleSheet("color:#aaaaaa;padding:2px 4px;")
        self.chk_online = QCheckBox("本次联网翻译")
        self.chk_online.setChecked(False)
        self.chk_online.setStyleSheet("color:#cccccc;")
        self.chk_online.setToolTip("仅影响本次运行；下次启动仍默认离线")
        self.chk_online.toggled.connect(self._on_online_toggled)

        self.right = QWidget()
        self.right.setMinimumWidth(280)
        self.right.setMaximumWidth(480)
        self.right.setStyleSheet("background:#141414;")
        rv = QVBoxLayout(self.right)
        rv.setContentsMargins(8, 8, 8, 8)
        head = QHBoxLayout()
        self.lbl_title = QLabel("结果")
        self.lbl_title.setStyleSheet("color:#e6e6e6;font-weight:600;")
        head.addWidget(self.lbl_title)
        head.addStretch(1)
        btn_copy = QPushButton("复制选中")
        btn_copy.clicked.connect(self.copy_selected)
        btn_all = QPushButton("复制全部")
        btn_all.clicked.connect(self.copy_all)
        for b in (btn_copy, btn_all):
            b.setStyleSheet(
                "QPushButton{background:#2a2a2a;color:#ddd;border:1px solid #3a3a3a;padding:4px 8px;}"
                "QPushButton:hover{background:#333;}"
            )
            head.addWidget(b)
        rv.addLayout(head)
        rv.addWidget(self.chk_online)
        rv.addWidget(self.result, 1)
        rv.addWidget(self.status)

        self.split = QSplitter()
        self.split.addWidget(self.scroll)
        self.split.addWidget(self.right)
        self.split.setStretchFactor(0, 1)
        self.split.setStretchFactor(1, 0)
        # 主页面默认只显示截图，翻译结果侧栏按需展开
        self.right.hide()
        self.setCentralWidget(self.split)

        self._plain = ""
        self._worker: Optional[Worker] = None
        self._act_translate: Optional[QAction] = None
        self._pending_translate = False
        self._build_toolbar()
        self._bind_model_hub()
        self._fit_window_to_shot()
        # 模型状态只写在状态栏，避免右侧占位文案干扰「只看截图」
        self._refresh_model_panel(quiet=True)

    def _fit_window_to_shot(self):
        """窗口尽量贴合截图尺寸，突出截图本身。"""
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        img_w, img_h = self.canvas.base.size
        tb_h = 40
        # 预留少量边框，避免贴边难拖拽
        pad = 8
        win_w = img_w + pad * 2
        win_h = img_h + tb_h + pad * 2
        if avail:
            max_w = max(480, avail.width() - 40)
            max_h = max(320, avail.height() - 60)
            win_w = min(win_w, max_w)
            win_h = min(win_h, max_h)
            # 居中弹出
            x = avail.x() + (avail.width() - win_w) // 2
            y = avail.y() + (avail.height() - win_h) // 2
            self.setGeometry(x, y, win_w, win_h)
        else:
            self.resize(win_w, win_h)

    def _show_result_panel(self):
        """需要看翻译/OCR 结果时再展开右侧栏。"""
        if self.right.isHidden():
            self.right.setVisible(True)
            total = max(640, self.width())
            side = min(360, max(280, total // 3))
            self.split.setSizes([max(200, total - side), side])

    def _bind_model_hub(self):
        """订阅启动预加载进度，右侧栏实时提示。"""
        if self.model_hub is None:
            return
        self.model_hub.progress.connect(self._on_model_progress)
        self.model_hub.ready.connect(self._on_model_ready)

    def _refresh_model_panel(self, quiet: bool = False):
        """根据当前模型状态刷新提示；quiet 时不往结果区灌占位文案。"""
        online = self.chk_online.isChecked()
        if online:
            self.status.setText("联网翻译已开启")
            if self._act_translate:
                self._act_translate.setEnabled(True)
            return

        if translate_service.is_model_ready():
            tip = translate_service.get_model_status()
            self.status.setText(tip)
            self.lbl_title.setText("结果 · 模型已就绪")
            if self._act_translate:
                self._act_translate.setEnabled(True)
            if quiet or self._plain:
                return
            if (not self.right.isHidden()) and not self.result.toPlainText().strip():
                self.result.setTextColor(QColor("#4EC9B0"))
                self.result.setPlainText("✓ 离线翻译模型已就绪\n\n点击「对照翻译」即可。")
            return

        msg = translate_service.get_model_status() or "正在加载离线翻译模型…"
        self.status.setText(msg)
        self.lbl_title.setText("结果 · 模型加载中")
        if self._act_translate:
            self._act_translate.setEnabled(True)
        if quiet or self._plain or self.right.isHidden():
            return
        self.result.setTextColor(QColor("#DCDCAA"))
        self.result.setPlainText(
            "⏳ 正在加载离线翻译模型…\n\n"
            f"当前：{msg}"
        )

    def _on_model_progress(self, msg: str):
        if self.chk_online.isChecked():
            return
        self.status.setText(msg)
        if self._plain or self.right.isHidden():
            return
        self.result.setTextColor(QColor("#DCDCAA"))
        self.result.setPlainText(
            "⏳ 正在加载离线翻译模型…\n\n"
            f"当前：{msg}"
        )

    def _on_model_ready(self, ok: bool, msg: str):
        if self.chk_online.isChecked():
            return
        self._refresh_model_panel(quiet=self.right.isHidden())
        if ok:
            self.status.setText("离线翻译模型已就绪，可以使用对照翻译")
            if (not self.right.isHidden()) and not self._plain:
                self.result.setTextColor(QColor("#4EC9B0"))
                self.result.setPlainText("✓ 离线翻译模型已就绪\n\n点击「对照翻译」即可。")
            if self._pending_translate:
                self._pending_translate = False
                self._start_worker(True)
        else:
            self.status.setText(f"模型加载失败：{msg}")
            self._show_result_panel()
            if not self._plain:
                self.result.setTextColor(QColor("#F44747"))
                self.result.setPlainText(f"✗ 离线翻译模型加载失败\n\n{msg}")
            self._pending_translate = False

    def _on_online_toggled(self, checked: bool):
        self.settings.use_online = bool(checked)
        save_settings(self.settings)
        mode = "联网" if checked else "离线本机"
        self.status.setText(f"已切换：{mode}")
        # 只更新状态文字，不强制打开侧栏
        self._refresh_model_panel(quiet=True)

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
        ]:
            a = QAction(name, self)
            a.triggered.connect(slot)
            tb.addAction(a)
        # 对照翻译单独保留引用，便于按模型状态提示
        self._act_translate = QAction("对照翻译", self)
        self._act_translate.triggered.connect(lambda: self.run_job(True))
        tb.addAction(self._act_translate)

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
        use_online = self.chk_online.isChecked()
        self.settings.use_online = use_online
        # 点提取/翻译时才展开结果侧栏，主页面仍以截图为主
        self._show_result_panel()

        # 离线对照翻译：模型未就绪时先提示并排队等待
        if do_translate and not use_online and not translate_service.is_model_ready():
            self._pending_translate = True
            msg = translate_service.get_model_status() or "正在加载离线翻译模型…"
            self.status.setText(f"模型加载中，加载完成后自动开始翻译…（{msg}）")
            self.result.setTextColor(QColor("#DCDCAA"))
            self.result.setPlainText(
                "⏳ 正在加载离线翻译模型…\n\n"
                "加载完成后将自动开始对照翻译。\n\n"
                f"当前：{msg}"
            )
            if not translate_service.is_model_loading():
                self._kick_preload()
            return

        self._pending_translate = False
        self._start_worker(do_translate)

    def _kick_preload(self):
        """编辑器内兜底触发预加载（启动预加载失败时）。"""
        class _LocalPreload(QThread):
            progress = Signal(str)
            finished_ok = Signal(bool, str)

            def run(self_inner):
                ok, msg = translate_service.preload_offline_models(
                    progress=lambda s: self_inner.progress.emit(s),
                )
                self_inner.finished_ok.emit(ok, msg)

        self._local_preload = _LocalPreload()
        self._local_preload.progress.connect(self._on_model_progress)
        self._local_preload.finished_ok.connect(self._on_model_ready)
        self._local_preload.start()

    def _start_worker(self, do_translate: bool):
        img = self.canvas.compose()
        use_online = self.chk_online.isChecked()
        self._worker = Worker(img, do_translate, use_online)
        self._worker.status.connect(self.status.setText)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(lambda e: QMessageBox.warning(self, "失败", e))
        if do_translate and not use_online:
            self.status.setText("离线翻译模型已就绪，开始对照翻译…")
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
