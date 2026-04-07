"""
Source selection dialog shown at application startup.

Allows the user to choose between:
  1. IP / RTSP camera
  2. Webcam / USB camera (incl. Camo Studio virtual camera)
  3. Video file
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class SourceSelectionDialog(QDialog):
    """Modal dialog to select the video source before the main window opens."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор источника видео")
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        # Result fields — filled when the user confirms
        self.source = None        # "ip" | "webcam" | "file"
        self.camera_url = None    # str (IP/RTSP URL) | int (webcam index) | str (file path)
        self.camera_name = None   # str
        self.fps = 30
        self.resolution = (1280, 720)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)

        # ── Radio buttons ────────────────────────────────────────────────
        root.addWidget(QLabel("<b>Выберите источник видео:</b>"))

        self.radio_ip = QRadioButton("IP / RTSP камера")
        self.radio_webcam = QRadioButton("Веб-камера / USB-камера (Camo Studio и др.)")
        self.radio_file = QRadioButton("Видеофайл")
        self.radio_ip.setChecked(True)

        btn_group = QButtonGroup(self)
        for rb in (self.radio_ip, self.radio_webcam, self.radio_file):
            btn_group.addButton(rb)
            root.addWidget(rb)

        # ── Panels (one per source type) ─────────────────────────────────
        self.panel_ip = self._build_ip_panel()
        self.panel_webcam = self._build_webcam_panel()
        self.panel_file = self._build_file_panel()

        for panel in (self.panel_ip, self.panel_webcam, self.panel_file):
            root.addWidget(panel)

        self._show_panel(self.panel_ip)

        # ── Common: name / fps / resolution ──────────────────────────────
        root.addWidget(self._h_line())
        form = QFormLayout()
        form.setSpacing(6)

        self.le_name = QLineEdit("Камера 1")
        form.addRow("Имя:", self.le_name)

        self.sb_fps = QSpinBox()
        self.sb_fps.setRange(1, 120)
        self.sb_fps.setValue(30)
        form.addRow("FPS:", self.sb_fps)

        self.le_resolution = QLineEdit("1280 720")
        self.le_resolution.setPlaceholderText("ширина высота")
        form.addRow("Разрешение:", self.le_resolution)

        root.addLayout(form)

        # ── Confirm button ────────────────────────────────────────────────
        root.addWidget(self._h_line())
        btn_ok = QPushButton("Подтвердить")
        btn_ok.setDefault(True)
        btn_ok.setFixedHeight(36)
        root.addWidget(btn_ok)

        # ── Signals ───────────────────────────────────────────────────────
        self.radio_ip.toggled.connect(lambda on: on and self._show_panel(self.panel_ip))
        self.radio_webcam.toggled.connect(lambda on: on and self._show_panel(self.panel_webcam))
        self.radio_file.toggled.connect(lambda on: on and self._show_panel(self.panel_file))
        btn_ok.clicked.connect(self._on_confirm)

    def _build_ip_panel(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(0, 0, 0, 0)
        self.le_ip_url = QLineEdit()
        self.le_ip_url.setPlaceholderText("rtsp://192.168.1.10:554/stream  или  http://...")
        form.addRow("URL / IP:", self.le_ip_url)
        return w

    def _build_webcam_panel(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(0, 0, 0, 0)
        self.sb_cam_index = QSpinBox()
        self.sb_cam_index.setRange(0, 10)
        self.sb_cam_index.setValue(0)
        self.sb_cam_index.setToolTip(
            "0 — первая камера (встроенная).  "
            "Camo Studio обычно занимает индекс 1 или 2."
        )
        form.addRow("Индекс камеры:", self.sb_cam_index)

        note = QLabel(
            "💡 Camo Studio создаёт виртуальную камеру.\n"
            "Если индекс 0 — встроенная, попробуйте 1 или 2."
        )
        note.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow(note)
        return w

    def _build_file_panel(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)

        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)

        self.le_file_path = QLineEdit()
        self.le_file_path.setPlaceholderText("Путь к видеофайлу...")
        self.le_file_path.setReadOnly(True)

        btn_browse = QPushButton("Обзор…")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self._browse_file)

        h.addWidget(self.le_file_path)
        h.addWidget(btn_browse)
        layout.addRow("Файл:", row)
        return w

    @staticmethod
    def _h_line() -> QWidget:
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet("background: #444;")
        return line

    def _show_panel(self, panel: QWidget):
        for p in (self.panel_ip, self.panel_webcam, self.panel_file):
            p.setVisible(p is panel)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите видеофайл",
            "",
            "Видео (*.mp4 *.avi *.mov *.mkv *.webm);;Все файлы (*)",
        )
        if path:
            self.le_file_path.setText(path)

    def _on_confirm(self):
        # Parse resolution
        try:
            w, h = map(int, self.le_resolution.text().split())
            self.resolution = (w, h)
        except ValueError:
            self.resolution = (1280, 720)

        self.fps = self.sb_fps.value()
        self.camera_name = self.le_name.text() or "Камера 1"

        if self.radio_ip.isChecked():
            url = self.le_ip_url.text().strip()
            if not url:
                self.le_ip_url.setPlaceholderText("⚠ Введите URL камеры!")
                return
            self.source = "ip"
            self.camera_url = url

        elif self.radio_webcam.isChecked():
            self.source = "webcam"
            self.camera_url = self.sb_cam_index.value()   # int index

        else:
            path = self.le_file_path.text().strip()
            if not path:
                self.le_file_path.setPlaceholderText("⚠ Выберите файл!")
                return
            self.source = "file"
            self.camera_url = path

        self.accept()
