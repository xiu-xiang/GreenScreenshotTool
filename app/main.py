"""绿色便携截图工具入口：托盘常驻、默认离线、热键截图。"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon, QWidget

from app.capture import select_region
from app.editor import EditorWindow
from app.paths import app_root, models_dir
from app.settings import load_settings, save_settings
from app import translate_service


class HotkeyBridge(QObject):
    """把热键回调切回 Qt 主线程。"""

    triggered = Signal()


class ModelHub(QObject):
    """离线翻译模型加载状态总线（托盘 / 编辑器共用）。"""

    progress = Signal(str)
    ready = Signal(bool, str)  # ok, message


class PreloadWorker(QThread):
    """启动后后台预热离线翻译模型。"""

    progress = Signal(str)
    finished_ok = Signal(bool, str)

    def run(self):
        ok, msg = translate_service.preload_offline_models(
            progress=lambda s: self.progress.emit(s),
        )
        self.finished_ok.emit(ok, msg)


def _load_icon() -> QIcon:
    icon_path = app_root() / "assets" / "app.ico"
    if icon_path.exists():
        return QIcon(str(icon_path))
    # 回退：简单色块
    from PySide6.QtGui import QPixmap, QPainter, QColor

    pix = QPixmap(64, 64)
    pix.fill(QColor("#2D2D30"))
    p = QPainter(pix)
    p.setPen(QColor("#00AEEF"))
    p.drawRect(12, 12, 40, 40)
    p.end()
    return QIcon(pix)


class AppController(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.settings = load_settings()
        # 启动强制离线
        self.settings.use_online = False
        save_settings(self.settings)

        # 预先把离线翻译目录指到 models/argos
        translate_service.setup_offline_env()

        self.model_hub = ModelHub()
        self.app.setProperty("model_hub", self.model_hub)

        self.bridge = HotkeyBridge()
        self.bridge.triggered.connect(self.start_capture)

        self.tray = QSystemTrayIcon(_load_icon(), app)
        self.tray.setToolTip(f"绿色截图工具（离线） 热键 {self.settings.hotkey}\n模型：加载中…")
        menu = QMenu()
        act_cap = QAction(f"开始截图 ({self.settings.hotkey})", self)
        act_cap.triggered.connect(self.start_capture)
        act_about = QAction("关于", self)
        act_about.triggered.connect(self.show_about)
        act_quit = QAction("退出", self)
        act_quit.triggered.connect(app.quit)
        menu.addAction(act_cap)
        menu.addAction(act_about)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        self.tray.showMessage(
            "绿色截图工具已启动",
            f"默认离线本机运行。热键：{self.settings.hotkey}\n正在后台加载翻译模型…",
            QSystemTrayIcon.MessageIcon.Information,
            3500,
        )

        self._listener = None
        self._capturing = False
        self._editors = []
        self._start_hotkey()
        self._start_model_preload()

    def _start_model_preload(self):
        """启动即后台加载模型，避免点对照翻译时才卡住。"""
        self._preload = PreloadWorker()
        self._preload.progress.connect(self._on_model_progress)
        self._preload.finished_ok.connect(self._on_model_ready)
        self._preload.start()

    def _on_model_progress(self, msg: str):
        self.tray.setToolTip(f"绿色截图工具（离线） 热键 {self.settings.hotkey}\n{msg}")
        self.model_hub.progress.emit(msg)

    def _on_model_ready(self, ok: bool, msg: str):
        tip = msg if ok else f"模型加载失败：{msg}"
        self.tray.setToolTip(f"绿色截图工具（离线） 热键 {self.settings.hotkey}\n{tip}")
        self.model_hub.ready.emit(ok, msg)
        self.tray.showMessage(
            "离线翻译模型已就绪" if ok else "离线翻译模型加载失败",
            tip,
            QSystemTrayIcon.MessageIcon.Information if ok else QSystemTrayIcon.MessageIcon.Warning,
            4000,
        )

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.start_capture()

    def _start_hotkey(self):
        # pynput 全局热键
        try:
            from pynput import keyboard

            # 默认 ctrl+alt+a
            mapping = {
                "ctrl+alt+a": (keyboard.Key.ctrl, keyboard.Key.alt, keyboard.KeyCode.from_char("a")),
            }
            # 使用 GlobalHotKeys
            hotkey = self.settings.hotkey.lower().replace(" ", "")
            if hotkey not in mapping:
                hotkey = "ctrl+alt+a"

            def on_activate():
                self.bridge.triggered.emit()

            self._listener = keyboard.GlobalHotKeys({ "<ctrl>+<alt>+a": on_activate })
            self._listener.start()
        except Exception as ex:
            QMessageBox.warning(
                None,
                "热键",
                f"全局热键注册失败：{ex}\n仍可通过托盘菜单截图。",
            )

    def start_capture(self):
        if self._capturing:
            return
        self._capturing = True
        try:
            img = select_region()
            if img is not None:
                # 每次打开编辑器前刷新设置（保持会话内联网勾选）
                win = EditorWindow(img, self.settings, model_hub=self.model_hub)
                win.show()
                self._editors.append(win)
        finally:
            self._capturing = False

    def show_about(self):
        ok = translate_service.is_model_ready()
        msg = translate_service.get_model_status()
        err = translate_service.get_model_error() or ""
        QMessageBox.information(
            None,
            "关于",
            "绿色便携截图工具 v1.0\n\n"
            "· 默认离线本机运行（OCR + 翻译模型随包）\n"
            "· 启动后后台预加载翻译模型\n"
            "· 可在编辑器勾选「本次使用联网翻译」\n"
            "· 下次启动仍恢复离线\n"
            "· 支持 Win10+ x64，无需安装 Python/Docker\n\n"
            f"热键：{self.settings.hotkey}\n"
            f"模型：{models_dir()}\n"
            f"离线翻译：{'就绪' if ok else '未就绪 / 加载中'}\n"
            f"{msg}\n{err}",
        )


def run():
    # HiDPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("ShotPortable")
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "错误", "系统托盘不可用")
        return 1
    _ = AppController(app)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
