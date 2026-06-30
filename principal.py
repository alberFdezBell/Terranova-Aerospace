"""
Terranova Aerospace command center.

Entry point for authentication, startup loading, command navigation, and
internal/external module launching.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import random
import subprocess
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QSize, Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QPalette, QFont, QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QScrollArea,
)

# Importación condicional del módulo orbital (requiere krpc, pyqtgraph, numpy)
try:
    import numpy as np
    import krpc
    import pyqtgraph.opengl as gl
    _KSP_AVAILABLE = True
except Exception:  # ImportError, ModuleNotFoundError, etc.
    _KSP_AVAILABLE = False
    np = None  # type: ignore
    krpc = None  # type: ignore
    gl = None  # type: ignore


APP_NAME = "Terranova Aerospace"
BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "icons" / "tas.png"
LOGO_PATH_CORT = BASE_DIR / "icons" / "tas_cortado.png"
CONFIG_DIR = BASE_DIR / "config"
USER_FILE = CONFIG_DIR / "user.dat"

HASH_ITERATIONS = 240_000

MODULES: dict[str, str | None] = {
    "Mapa orbital": "internal",
    "Notas de prensa": None,
    "Programación": None,
    "Centro de mando": None,
    "Personal": None,
}

INITIAL_STATUS = [
    "Inicializando sistemas...",
    "Verificando credenciales de operador...",
    "Sincronizando telemetría interna...",
    "Conectando con el centro de mando...",
    "Preparando paneles de navegación...",
]

MODULE_STATUS = [
    "Cargando mapa orbital...",
    "Sincronizando satélites...",
    "Estableciendo conexión...",
    "Validando subsistemas...",
    "Transferencia de control en curso...",
]


def apply_shadow(widget: QWidget, blur: int = 28, alpha: int = 90) -> None:
    # Se elimina el efecto de sombreado (remarcado oscuro) para dejar la interfaz plana
    pass


def fade_in(widget: QWidget, duration: int = 700) -> None:
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    widget._fade_animation = animation
    animation.start()


def fade_out(widget: QWidget, finished, duration: int = 420) -> None:
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    effect.setOpacity(1.0)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(1.0)
    animation.setEndValue(0.0)
    animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
    animation.finished.connect(finished)
    widget._fade_animation = animation
    animation.start()


class AuthManager:
    """Local first-run authentication with salted PBKDF2 password storage."""

    def __init__(self, user_file: Path = USER_FILE):
        self.user_file = user_file

    def has_user(self) -> bool:
        return self.user_file.exists()

    def load_user(self) -> dict:
        with self.user_file.open("r", encoding="utf-8") as file:
            return json.load(file)

    def username(self) -> str | None:
        if not self.has_user():
            return None
        try:
            return self.load_user().get("username")
        except (OSError, json.JSONDecodeError):
            return None

    def create_user(self, username: str, password: str) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        salt = os.urandom(32)
        digest = self._hash_password(password, salt, HASH_ITERATIONS)
        payload = {
            "username": username.strip(),
            "algorithm": "PBKDF2-HMAC-SHA256",
            "iterations": HASH_ITERATIONS,
            "salt": base64.b64encode(salt).decode("ascii"),
            "password_hash": base64.b64encode(digest).decode("ascii"),
        }
        with self.user_file.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)

    def verify_password(self, password: str) -> bool:
        try:
            payload = self.load_user()
            salt = base64.b64decode(payload["salt"])
            expected = base64.b64decode(payload["password_hash"])
            iterations = int(payload["iterations"])
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            return False

        digest = self._hash_password(password, salt, iterations)
        return hmac.compare_digest(digest, expected)

    @staticmethod
    def _hash_password(password: str, salt: bytes, iterations: int) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


class LogoLabel(QLabel):
    def __init__(self, max_size: QSize, parent: QWidget | None = None):
        super().__init__(parent)
        self.max_size = max_size
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(QSize(120, 80))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._pixmap = QPixmap(str(LOGO_PATH_CORT)) if LOGO_PATH_CORT.exists() else QPixmap()
        self._refresh()

    def resizeEvent(self, event) -> None:
        self._refresh()
        super().resizeEvent(event)

    def _refresh(self) -> None:
        if not self._pixmap.isNull():
            target = self._pixmap.scaled(
                self.max_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
                )
            self.setPixmap(target)
            self.setText("")
        else:
            self.setPixmap(QPixmap())
            self.setText(APP_NAME)
            self.setStyleSheet("color: #dce9f6; font-size: 24px; font-weight: 700;")


class SpinnerWidget(QWidget):
    def __init__(self, size: int = 64, parent: QWidget | None = None):
        super().__init__(parent)
        self.angle = 0
        self.setFixedSize(size, size)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(24)

    def _tick(self) -> None:
        self.angle = (self.angle + 7) % 360
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        margin = 7
        rect = self.rect().adjusted(margin, margin, -margin, -margin)

        base_pen = QPen(QColor(58, 79, 100, 150), 4)
        base_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(base_pen)
        painter.drawArc(rect, 0, 360 * 16)

        active_pen = QPen(QColor(111, 196, 233), 4)
        active_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(active_pen)
        painter.drawArc(rect, -self.angle * 16, 105 * 16)


class OrbitalLoader(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.angle = 0.0
        self.setFixedSize(138, 138)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def _tick(self) -> None:
        self.angle = (self.angle + 2.4) % 360
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        radius = 48

        painter.setPen(QPen(QColor(79, 112, 139, 150), 1))
        painter.drawEllipse(center, radius, radius)
        painter.drawEllipse(center, radius - 17, radius - 17)

        painter.setPen(QPen(QColor(112, 207, 225), 2))
        painter.drawArc(QRect(center.x() - radius, center.y() - radius, radius * 2, radius * 2), 35 * 16, 160 * 16)

        x = center.x() + math.cos(math.radians(self.angle)) * radius
        y = center.y() + math.sin(math.radians(self.angle)) * radius
        painter.setBrush(QColor(151, 242, 222))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(x) - 5, int(y) - 5, 10, 10)


class GlassPanel(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("glassPanel")
        apply_shadow(self)


class LoginScreen(QWidget):
    def __init__(self, auth: AuthManager, on_success, parent: QWidget | None = None):
        super().__init__(parent)
        self.auth = auth
        self.on_success = on_success
        self.is_first_run = not auth.has_user()
        self._build_ui()
        fade_in(self.panel)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.panel = GlassPanel()
        self.panel.setMaximumWidth(500)
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(42, 38, 42, 38)
        panel_layout.setSpacing(18)

        panel_layout.addWidget(LogoLabel(QSize(270, 130)))

        title = QLabel("Configuración del operador" if self.is_first_run else "Acceso de operador")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("title")
        panel_layout.addWidget(title)

        subtitle_text = (
            "Primer inicio del sistema Terranova Aerospace"
            if self.is_first_run
            else f"Usuario detectado: {self.auth.username() or 'Operador'}"
        )
        subtitle = QLabel(subtitle_text)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setObjectName("muted")
        panel_layout.addWidget(subtitle)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Nombre de usuario")
        self.username_input.setVisible(self.is_first_run)
        panel_layout.addWidget(self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Contraseña")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.returnPressed.connect(self.submit)
        panel_layout.addWidget(self.password_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("error")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel_layout.addWidget(self.error_label)

        button = QPushButton("Iniciar sesión" if not self.is_first_run else "Guardar operador")
        button.setObjectName("primaryButton")
        button.clicked.connect(self.submit)
        panel_layout.addWidget(button)

        layout.addWidget(self.panel)

    def submit(self) -> None:
        password = self.password_input.text()
        if self.is_first_run:
            username = self.username_input.text().strip()
            if len(username) < 3 or len(password) < 6:
                self._set_error("Usuario mínimo 3 caracteres y contraseña mínimo 6.")
                return
            try:
                self.auth.create_user(username, password)
            except OSError as exc:
                self._set_error(f"No se pudo guardar la configuración: {exc}")
                return
            self.on_success()
            return

        if self.auth.verify_password(password):
            self.on_success()
        else:
            self._set_error("Credenciales no válidas.")

    def _set_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.password_input.selectAll()
        self.password_input.setFocus()


class StartupLoadingScreen(QWidget):
    def __init__(self, on_finished, ksp_callbacks=None, parent: QWidget | None = None):
        """
        Parámetros
        ----------
        on_finished : callable
            Se llama al terminar el tiempo de carga.
        ksp_callbacks : tuple[callable, callable] | None
            Par ``(on_success, on_failure)`` para iniciar la conexión KSP
            en background durante la pantalla de carga.
            Si es ``None`` no se intenta ninguna conexión.
        """
        super().__init__(parent)
        self.on_finished = on_finished
        self.ksp_callbacks = ksp_callbacks
        self.messages = INITIAL_STATUS
        self._ksp_thread = None  # Mantener referencia para evitar GC prematuro
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(22)

        # LOGO MÁS GRANDE EN LA PANTALLA DE CARGA
        self.logo = LogoLabel(QSize(550, 250))

        self.spinner = SpinnerWidget(74)
        self.status = QLabel(self.messages[0])
        self.status.setObjectName("status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.logo)
        layout.addWidget(self.spinner, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

    def start(self) -> None:
        fade_in(self.logo, 850)

        # Iniciar conexión KSP en hilo de fondo si está disponible
        if _KSP_AVAILABLE and self.ksp_callbacks is not None and connect_to_ksp_async is not None:
            on_success, on_failure = self.ksp_callbacks
            self._ksp_thread = connect_to_ksp_async(on_success, on_failure)

        duration = random.randint(3000, 7000)
        self.message_timer = QTimer(self)
        self.message_timer.timeout.connect(self._next_message)
        self.message_timer.start(850)
        QTimer.singleShot(duration, self._finish)

    def _next_message(self) -> None:
        self.status.setText(random.choice(self.messages))

    def _finish(self) -> None:
        self.message_timer.stop()
        self.on_finished()


class ModuleCard(QPushButton):
    def __init__(self, title: str, available: bool, parent: QWidget | None = None):
        super().__init__(title, parent)
        self.available = available
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(118)
        self.setObjectName("moduleCard" if available else "moduleCardDisabled")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._base_geometry = QRect()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._animate_hover(True)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._animate_hover(False)

    def _animate_hover(self, active: bool) -> None:
        if not self.isEnabled():
            return
        if self._base_geometry.isNull():
            self._base_geometry = self.geometry()
        rect = self._base_geometry.adjusted(-3, -3, 3, 3) if active else self._base_geometry
        animation = QPropertyAnimation(self, b"geometry", self)
        animation.setDuration(150)
        animation.setEndValue(rect)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_animation = animation
        animation.start()


class CommandCenter(QWidget):
    def __init__(self, on_module_selected, parent: QWidget | None = None):
        super().__init__(parent)
        self.on_module_selected = on_module_selected
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(42, 34, 42, 36)
        root.setSpacing(28)

        # 1. Contenedor superior (Header) transparente
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        # 2. Logo del panel de control aún más grande y centrado
        logo = LogoLabel(QSize(500, 180))
        header_layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignCenter)

        # 3. Añadir el Header al diseño raíz
        root.addWidget(header)
        
        # 4. SEPARACIÓN EXTRA: Añadimos un espacio en píxeles entre el logo y los botones
        root.addSpacing(40)

        # 5. Grid de módulos
        grid = QGridLayout()
        grid.setSpacing(18)
        for index, (name, target) in enumerate(MODULES.items()):
            card = ModuleCard(name, bool(target))
            card.clicked.connect(lambda checked=False, module=name: self.on_module_selected(module))
            row, col = divmod(index, 3)
            grid.addWidget(card, row, col)
            
        root.addLayout(grid)
        root.addStretch()


class ModuleTransitionScreen(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.module_name = ""
        self.target_file: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)
        # Misma estética que StartupLoadingScreen
        layout.addWidget(LogoLabel(QSize(550, 250)), alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(SpinnerWidget(74), alignment=Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel("Preparando modulo")
        self.title.setObjectName("transitionTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status = QLabel(MODULE_STATUS[0])
        self.status.setObjectName("status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)
        layout.addWidget(self.status)

    def start(self, module_name: str, target_file: str, on_launch) -> None:
        self.module_name = module_name
        self.target_file = target_file
        self.title.setText(module_name)
        self.status.setText(MODULE_STATUS[0])
        fade_in(self, 360)

        self.message_timer = QTimer(self)
        self.message_timer.timeout.connect(lambda: self.status.setText(random.choice(MODULE_STATUS)))
        self.message_timer.start(300)
        QTimer.singleShot(900, lambda: self._launch(on_launch))

    def _launch(self, on_launch) -> None:
        self.message_timer.stop()
        on_launch(self.module_name, self.target_file)


# ─── Clases del visualizador orbital en tiempo real (condicional) ─────────────

if _KSP_AVAILABLE:
    # Paletas y constantes específicas del mapa
    VESSEL_COLORS = [
        (0.0, 1.0, 0.45, 0.8),   # Verde neón
        (0.0, 0.75, 1.0, 0.8),   # Azul celeste
        (1.0, 0.55, 0.0, 0.8),   # Naranja
        (0.9, 0.0, 0.9, 0.8),    # Magenta
        (1.0, 1.0, 0.0, 0.8),    # Amarillo
        (0.0, 1.0, 1.0, 0.8),    # Cian
        (1.0, 0.2, 0.5, 0.8),    # Rosa
        (0.5, 1.0, 0.0, 0.8),    # Lima
    ]
    DOT_COLORS = [
        (0.0, 1.0, 0.45, 1.0),
        (0.0, 0.75, 1.0, 1.0),
        (1.0, 0.55, 0.0, 1.0),
        (0.9, 0.0, 0.9, 1.0),
        (1.0, 1.0, 0.0, 1.0),
        (0.0, 1.0, 1.0, 1.0),
        (1.0, 0.2, 0.5, 1.0),
        (0.5, 1.0, 0.0, 1.0),
    ]

    TRAIL_LEN = 80       # Número de puntos en el rastro de la nave
    ORBIT_POINTS = 150   # Resolución de la curva orbital
    KERBIN_RADIUS_KM = 600.0
    PLANET_DRAW_RADIUS = 600
    EQUATORIAL_RING_RADIUS = 468.0
    AXIS_HALF_LEN = 720.0
    ORBIT_LINE_COLOR = (0.0, 0.82, 0.88, 1.0)

    class ConnectThread(QThread):
        success = pyqtSignal(object)
        failure = pyqtSignal(str)

        def run(self):
            try:
                conn = krpc.connect(name='Orbit Visualizer', address='127.0.0.1', rpc_port=50000)
                self.success.emit(conn)
            except Exception as e:
                self.failure.emit(str(e))

    def connect_to_ksp_async(on_success, on_failure):
        thread = ConnectThread()
        thread.success.connect(on_success)
        thread.failure.connect(on_failure)
        thread.start()
        return thread

    class VesselInfoCard(QFrame):
        clicked = pyqtSignal(str)

        def __init__(self, name: str, color_rgba: tuple, parent=None):
            super().__init__(parent)
            self.vessel_name = name
            self._base_hex = "#{:02X}{:02X}{:02X}".format(int(color_rgba[0]*255), int(color_rgba[1]*255), int(color_rgba[2]*255))
            self._selected = False
            self._apply_style()

            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 6, 8, 6)
            layout.setSpacing(2)

            title = QLabel(f"🛰  {name}")
            title.setStyleSheet(f"color: {self._base_hex}; font-weight: bold; font-size: 11px;")
            layout.addWidget(title)

            self.lbl_alt     = self._make_data_label("Altitud",    "—")
            self.lbl_period  = self._make_data_label("Período",    "—")
            self.lbl_inc     = self._make_data_label("Inclinación","—")
            self.lbl_ecc     = self._make_data_label("Excentr.",   "—")
            self.lbl_vel     = self._make_data_label("Velocidad",  "—")

            for w in (self.lbl_alt, self.lbl_period, self.lbl_inc, self.lbl_ecc, self.lbl_vel):
                layout.addWidget(w)

            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self._title = title

        def _apply_style(self):
            border = self._base_hex if self._selected else f"{self._base_hex}55"
            left = self._base_hex if self._selected else self._base_hex
            bg = "#223042" if self._selected else "#1a1e2a"
            self.setStyleSheet(f"""
                QFrame {{
                    background: {bg};
                    border: 1px solid {border};
                    border-left: 3px solid {left};
                    border-radius: 6px;
                    margin: 2px 4px;
                }}
            """)

        def set_selected(self, selected: bool):
            self._selected = selected
            self._apply_style()

        def _make_data_label(self, key: str, value: str) -> QLabel:
            lbl = QLabel(f"<span style='color:#666'>{key}:</span> <span style='color:#ddd'>{value}</span>")
            lbl.setStyleSheet("font-size: 10px;")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            return lbl

        def update_data(self, alt_km, period_s, inc_deg, ecc, vel_ms):
            def _set(lbl, key, value):
                lbl.setText(f"<span style='color:#666'>{key}:</span> <span style='color:#ddd'>{value}</span>")

            _set(self.lbl_alt,    "Altitud",     f"{alt_km:,.0f} km")
            _set(self.lbl_period, "Período",     self._fmt_time(period_s))
            _set(self.lbl_inc,    "Inclinación", f"{math.degrees(inc_deg):.2f}°")
            _set(self.lbl_ecc,    "Excentr.",    f"{ecc:.4f}")
            _set(self.lbl_vel,    "Velocidad",   f"{vel_ms:,.0f} m/s")

        def mousePressEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                self.clicked.emit(self.vessel_name)
            super().mousePressEvent(event)

        @staticmethod
        def _fmt_time(seconds: float) -> str:
            if seconds <= 0:
                return "—"
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            if h > 0:
                return f"{h}h {m:02d}m {s:02d}s"
            return f"{m}m {s:02d}s"

    class KSPRealTimeVisualizer(QWidget):
        back_clicked = pyqtSignal()

        def __init__(self, conn=None, parent=None):
            super().__init__(parent)
            self.setWindowTitle("KSP Orbit Tracker")
            self._apply_dark_theme()

            self.conn = None
            self.connect_thread = None
            self.render_objects: dict = {}
            self.vessel_streams: dict = {}
            self.color_counter = 0
            self._camera_fitted = False
            self.active_filter_text = ""
            self.selected_vessel = None
            self.info_bubble = None
            self.info_bubble_locked = False
            self.hovered_vessel = None
            self.last_press_pos = None

            self.last_mouse_pos = None
            self.is_rotating = False

            self._build_ui()
            self._init_static_scene()

            self.timer = QTimer(self)
            self.timer.timeout.connect(self._update_orbits)

            if conn is not None:
                self._on_connected(conn)

        def set_connection(self, conn):
            self._on_connected(conn)

        def _apply_dark_theme(self):
            self.setStyleSheet("""
                QWidget {
                    background: #0d1117;
                    color: #c9d1d9;
                    font-family: 'Segoe UI', 'SF Pro Display', sans-serif;
                }
                QPushButton {
                    background: #21262d;
                    color: #c9d1d9;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    padding: 5px 14px;
                    font-size: 12px;
                }
                QPushButton:hover  { background: #30363d; border-color: #58a6ff; }
                QPushButton:pressed { background: #161b22; }
                QPushButton:disabled { color: #484f58; }
                QPushButton#btnBack {
                    background: transparent;
                    border: none;
                    color: #c9d1d9;
                    font-size: 14px;
                    font-weight: bold;
                    text-decoration: none;
                    padding: 0px;
                }
                QPushButton#btnBack:hover {
                    background: transparent;
                    border: none;
                    color: #58a6ff;
                    text-decoration: underline;
                }
                QPushButton#btnBack:pressed {
                    background: transparent;
                    color: #1f6feb;
                }
                QLabel { color: #8b949e; }
                QScrollArea { border: none; background: transparent; }
                QScrollBar:vertical {
                    background: #161b22; width: 6px; border-radius: 3px;
                }
                QScrollBar::handle:vertical {
                    background: #30363d; border-radius: 3px;
                }
            """)

        def _build_ui(self):
            import os
            from PyQt6.QtGui import QPixmap  # Asegúrate de tener esta importación en tu archivo
            
            root_layout = QHBoxLayout(self)
            root_layout.setContentsMargins(0, 0, 0, 0)
            root_layout.setSpacing(0)

            left_panel = QWidget()
            left_panel.setFixedWidth(220)
            left_panel.setStyleSheet("background: #0d1117; border-right: 1px solid #21262d;")
            left_layout = QVBoxLayout(left_panel)
            left_layout.setContentsMargins(10, 14, 10, 10)
            left_layout.setSpacing(10)

            # --- REEMPLAZO: Título de texto por Imagen ---
            title = QLabel()
            
            # Construye la ruta absoluta hacia la carpeta /icons
            ruta_imagen = os.path.join(os.path.dirname(__file__), "icons", "tas_cortado.png")
            pixmap = QPixmap(ruta_imagen)
            
            if not pixmap.isNull():
                # Redimensiona la imagen para que quepa en el panel (220px de ancho menos 20px de márgenes)
                ancho_maximo = 220 - 20
                pixmap_escalado = pixmap.scaledToWidth(ancho_maximo, Qt.TransformationMode.SmoothTransformation)
                title.setPixmap(pixmap_escalado)
                title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                # Fallback por si la imagen no se encuentra en el disco
                title.setText("[ ERROR: Imagen no encontrada ]")
                title.setStyleSheet("color: #ff7b72; font-size: 11px; font-weight: bold;")
            
            left_layout.addWidget(title)
            # ---------------------------------------------

            sep = self._make_separator()
            left_layout.addWidget(sep)

            # Dummy placeholders invisibles para mantener compatibilidad con el resto del código
            self.btn_connect = QPushButton()
            self.btn_connect.clicked.connect(self._connect_to_ksp)

            self.btn_disconnect = QPushButton()
            self.btn_disconnect.clicked.connect(self._disconnect)

            filter_lbl = QLabel("Buscar satélite:")
            filter_lbl.setStyleSheet("font-size: 10px; color: #6e7681;")
            left_layout.addWidget(filter_lbl)

            self.txt_filter = QLineEdit()
            self.txt_filter.setPlaceholderText("Ej. Way-E1")
            self.txt_filter.setClearButtonEnabled(True)
            self.txt_filter.textChanged.connect(self._apply_filter)
            self.txt_filter.setStyleSheet(
                "QLineEdit { background: #161b22; border: 1px solid #30363d; "
                "border-radius: 4px; color: #c9d1d9; padding: 4px 6px; font-size: 11px; }"
                "QLineEdit:focus { border-color: #58a6ff; }"
            )
            left_layout.addWidget(self.txt_filter)

            # Botón flotante "← Volver" en la esquina inferior derecha
            self.btn_back = QPushButton("← Volver", self)
            self.btn_back.setObjectName("btnBack")
            self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_back.clicked.connect(self._on_back_clicked)
            self.btn_back.adjustSize()
            self.btn_back.show()
            self.btn_back.raise_()

            self.lbl_status = QLabel("Desconectado")
            self.lbl_status.setStyleSheet("color: #6e7681; font-size: 11px;")
            self.lbl_status.setWordWrap(True)
            left_layout.addWidget(self.lbl_status)

            sep2 = self._make_separator()
            left_layout.addWidget(sep2)

            naves_hdr = QLabel("NAVES EN ÓRBITA")
            naves_hdr.setStyleSheet("font-size: 10px; color: #6e7681; letter-spacing: 1px;")
            left_layout.addWidget(naves_hdr)

            self.scroll = QScrollArea()
            self.scroll.setWidgetResizable(True)
            self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.cards_container = QWidget()
            self.cards_layout = QVBoxLayout(self.cards_container)
            self.cards_layout.setContentsMargins(0, 0, 0, 0)
            self.cards_layout.setSpacing(4)
            self.cards_layout.addStretch()
            self.scroll.setWidget(self.cards_container)
            self.scroll.setStyleSheet("background: transparent;")
            left_layout.addWidget(self.scroll, stretch=1)


            root_layout.addWidget(left_panel)

            right_panel = QWidget()
            right_layout = QVBoxLayout(right_panel)
            right_layout.setContentsMargins(0, 0, 0, 0)
            right_layout.setSpacing(0)

            top_bar = QWidget()
            top_bar_layout = QHBoxLayout(top_bar)
            top_bar_layout.setContentsMargins(10, 10, 10, 6)
            top_bar_layout.setSpacing(8)
            top_bar_layout.addStretch()

            self.btn_reload = QPushButton("↻  Recargar")
            self.btn_reload.setEnabled(False)
            self.btn_reload.clicked.connect(self._on_reload_clicked)
            self.btn_reload.setStyleSheet(
                "QPushButton { background: #1f6feb33; border-color: #1f6feb; color: #58a6ff; font-weight: bold; }"
                "QPushButton:hover { background: #1f6feb55; }"
            )
            top_bar_layout.addWidget(self.btn_reload)
            right_layout.addWidget(top_bar)

            self.view = gl.GLViewWidget()
            self.view.setBackgroundColor('#0d1117')
            self.view.setCameraPosition(distance=5200, elevation=22, azimuth=-45)
            self.view.setMouseTracking(True)

            self.info_bubble = QLabel(self.view)
            self.info_bubble.setTextFormat(Qt.TextFormat.RichText)
            self.info_bubble.setStyleSheet("""
                QLabel {
                    background: rgba(13, 17, 23, 225);
                    color: #e6edf3;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    padding: 7px 9px;
                    font-size: 11px;
                }
            """)
            self.info_bubble.hide()

            self.view.mouseMoveEvent    = self._mouse_move
            self.view.mousePressEvent   = self._mouse_press
            self.view.mouseReleaseEvent = self._mouse_release
            self.view.wheelEvent        = self._wheel_event

            right_layout.addWidget(self.view, stretch=1)
            root_layout.addWidget(right_panel, stretch=1)

        def _make_separator(self) -> QFrame:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("color: #21262d; margin: 2px 0;")
            return sep

        def _init_static_scene(self):
            md = gl.MeshData.sphere(rows=30, cols=48, radius=PLANET_DRAW_RADIUS)
            self.planet = gl.GLMeshItem(
                meshdata=md,
                smooth=True,
                color=(0.0, 0.55, 0.62, 1.0),
                edgeColor=None,
                drawEdges=False,
                drawFaces=True,
                shader='shaded',
                glOptions='opaque'
            )
            self.view.addItem(self.planet)

            rng = np.random.default_rng(42)
            phi   = rng.uniform(0, 2 * np.pi, 1200)
            theta = np.arccos(rng.uniform(-1, 1, 1200))
            dist  = rng.uniform(12000, 18000, 1200)
            stars = np.column_stack([
                dist * np.sin(theta) * np.cos(phi),
                dist * np.sin(theta) * np.sin(phi),
                dist * np.cos(theta)
            ]).astype(np.float32)
            star_sizes = rng.uniform(1.0, 2.5, 1200).astype(np.float32)
            star_colors = np.ones((1200, 4), dtype=np.float32)
            star_colors[:, 3] = rng.uniform(0.3, 0.9, 1200).astype(np.float32)
            self.stars = gl.GLScatterPlotItem(
                pos=stars, size=star_sizes, color=star_colors, pxMode=False, glOptions='opaque'
            )
            self.view.addItem(self.stars)
            self.stars.setDepthValue(-100)

        def _connect_to_ksp(self):
            self.btn_connect.setEnabled(False)
            self.lbl_status.setText("Conectando…")
            self.lbl_status.setStyleSheet("color: #d29922; font-size: 11px;")

            self.connect_thread = ConnectThread()
            self.connect_thread.success.connect(self._on_connected)
            self.connect_thread.failure.connect(self._on_connect_failed)
            self.connect_thread.start()

        def _on_connected(self, conn):
            self.conn = conn
            self.lbl_status.setText("Conectado  ●")
            self.lbl_status.setStyleSheet("color: #3fb950; font-size: 11px;")
            self.btn_disconnect.setEnabled(True)
            self.btn_reload.setEnabled(True)
            self._camera_fitted = False
            self._reload_data()
            self.timer.start(1000)

        def _on_connect_failed(self, err: str):
            self.lbl_status.setText(f"Error: {err}")
            self.lbl_status.setStyleSheet("color: #f85149; font-size: 11px;")
            self.btn_connect.setEnabled(True)

        def _disconnect(self):
            self.timer.stop()
            self._clear_all_vessels()

            if self.conn:
                try:
                    self.conn.close()
                except Exception:
                    pass
                self.conn = None

            self.lbl_status.setText("Desconectado")
            self.lbl_status.setStyleSheet("color: #6e7681; font-size: 11px;")
            self.btn_connect.setEnabled(True)
            self.btn_disconnect.setEnabled(False)
            self.btn_reload.setEnabled(False)
            self._camera_fitted = False

        def _clear_all_vessels(self):
            for vid, obj in self.render_objects.items():
                for key in ('line', 'dot', 'trail_line'):
                    if key in obj and obj[key] is not None:
                        try:
                            self.view.removeItem(obj[key])
                        except Exception:
                            pass
                if 'info_card' in obj and obj['info_card'] is not None:
                    obj['info_card'].deleteLater()

            self.render_objects.clear()

            for vid, streams in self.vessel_streams.items():
                for s in streams.values():
                    try:
                        s.remove()
                    except Exception:
                        pass
            self.vessel_streams.clear()
            self.color_counter = 0
            self._camera_fitted = False
            self.active_filter_text = ""
            self.selected_vessel = None
            self._hide_info_bubble()

        def _on_back_clicked(self):
            self.timer.stop()
            self.back_clicked.emit()

        def _set_selected_vessel(self, vessel_name: str):
            if vessel_name not in self.render_objects:
                return
            self.selected_vessel = vessel_name
            projected = self._project_vessel(vessel_name)
            if projected is not None:
                self.info_bubble_locked = True
                self._show_info_bubble(vessel_name, projected[0], projected[1])
            self._update_selection_visuals()

        def _project_point(self, point_3d):
            vw = self.view.width()
            vh = self.view.height()
            if vw <= 0 or vh <= 0:
                return None

            try:
                proj = self.view.projectionMatrix()
                view = self.view.viewMatrix()
            except Exception:
                return None

            def qmat_to_np(m):
                return np.array([m.data()[i] for i in range(16)], dtype=float).reshape(4, 4).T

            P = qmat_to_np(proj)
            V = qmat_to_np(view)
            MVP = P @ V

            x, y, z = point_3d
            clip = MVP @ np.array([x, y, z, 1.0])
            if clip[3] == 0:
                return None
            ndc = clip[:3] / clip[3]

            if ndc[2] < -1 or ndc[2] > 1:
                return None

            px = (ndc[0] + 1.0) * vw / 2.0
            py = (1.0 - ndc[1]) * vh / 2.0
            return px, py, clip[3]

        def _project_vessel(self, vessel_name: str):
            obj = self.render_objects.get(vessel_name)
            if obj is None or 'pos_3d' not in obj:
                return None
            return self._project_point(obj['pos_3d'])

        def _vessel_at_cursor(self, event, max_dist_px=14.0):
            best_vid = None
            best_dist = max_dist_px
            best_pos = None

            for vid, obj in self.render_objects.items():
                show_in_map = self.selected_vessel is None or self.selected_vessel == vid
                if not show_in_map:
                    continue

                projected = self._project_vessel(vid)
                if projected is None:
                    continue

                px, py, _ = projected
                dist = math.hypot(event.position().x() - px, event.position().y() - py)
                if dist < best_dist:
                    best_dist = dist
                    best_vid = vid
                    best_pos = (px, py)

            if best_vid is None:
                return None
            return best_vid, best_pos[0], best_pos[1]

        def _format_info_bubble(self, vessel_name: str) -> str:
            obj = self.render_objects.get(vessel_name, {})
            info = obj.get('info_data', {})
            cidx = obj.get('color_idx', 0)
            color = DOT_COLORS[cidx % len(DOT_COLORS)]
            color_hex = "#{:02X}{:02X}{:02X}".format(
                int(color[0] * 255),
                int(color[1] * 255),
                int(color[2] * 255)
            )
            return (
                f"<b style='color:{color_hex}'>🛰 {vessel_name}</b><br>"
                f"<span style='color:#8b949e'>Altitud:</span> {info.get('alt_km', 0):,.0f} km<br>"
                f"<span style='color:#8b949e'>Periodo:</span> {VesselInfoCard._fmt_time(info.get('period', 0))}<br>"
                f"<span style='color:#8b949e'>Inclinación:</span> {math.degrees(info.get('inc', 0)):.2f}°<br>"
                f"<span style='color:#8b949e'>Excentricidad:</span> {info.get('ecc', 0):.4f}<br>"
                f"<span style='color:#8b949e'>Velocidad:</span> {info.get('vel_ms', 0):,.0f} m/s"
            )

        def _show_info_bubble(self, vessel_name: str, px: float, py: float):
            if self.info_bubble is None:
                return
            self.info_bubble.setText(self._format_info_bubble(vessel_name))
            self.info_bubble.adjustSize()
            x = min(max(int(px) + 14, 8), max(8, self.view.width() - self.info_bubble.width() - 8))
            y = min(max(int(py) - self.info_bubble.height() - 12, 8), max(8, self.view.height() - self.info_bubble.height() - 8))
            self.info_bubble.move(x, y)
            self.info_bubble.show()

        def _hide_info_bubble(self):
            if self.info_bubble is not None:
                self.info_bubble.hide()
            self.hovered_vessel = None
            self.info_bubble_locked = False

        def _on_reload_clicked(self):
            if not self.conn:
                return
            self.btn_reload.setEnabled(False)
            for frame in ("↻  Recargando", "⟳  Recargando", "↺  Recargando"):
                self.btn_reload.setText(frame)
                QApplication.processEvents()
                time.sleep(0.04)
            self._reload_data()
            self.btn_reload.setEnabled(True)
            self.btn_reload.setText("↻  Recargar")

        def _update_selection_visuals(self):
            if self.selected_vessel is not None and self.selected_vessel not in self.render_objects:
                self.selected_vessel = None

            for vid, obj in self.render_objects.items():
                is_selected = self.selected_vessel == vid
                is_match = (
                    not self.active_filter_text or
                    self.active_filter_text in vid.lower()
                )
                show_in_map = self.selected_vessel is None or is_selected

                line = obj.get('line')
                dot = obj.get('dot')
                trail = obj.get('trail_line')
                card = obj.get('info_card')

                if line is not None:
                    line.setVisible(show_in_map)
                    if show_in_map:
                        base = obj.get('base_line_color')
                        if base is not None:
                            line.setData(pos=obj['orbit_pts'], color=base)

                if dot is not None:
                    dot.setVisible(show_in_map)
                    if show_in_map:
                        base = obj.get('base_dot_color')
                        if base is not None:
                            dot.setData(pos=np.array([obj['pos_3d']], dtype=np.float32), color=base)

                if trail is not None:
                    trail.setVisible(show_in_map)
                    trail_colors = obj.get('trail_colors')
                    if show_in_map and trail_colors is not None:
                        colors = trail_colors.copy()
                        colors[:, 3] = colors[:, 3]
                        trail.setData(pos=obj['trail_buf'], color=colors)

                if card is not None:
                    card.setVisible(is_match)
                    card.set_selected(is_selected)

        def _apply_filter(self, text: str):
            self.active_filter_text = (text or "").strip().lower()
            if self.selected_vessel is not None and self.active_filter_text and self.active_filter_text not in self.selected_vessel.lower():
                self.selected_vessel = None
                self._hide_info_bubble()
            self._update_selection_visuals()

        def _reload_data(self):
            if not self.conn:
                return

            self.lbl_status.setText("Recargando…")
            self.lbl_status.setStyleSheet("color: #d29922; font-size: 11px;")
            QApplication.processEvents()

            for obj in self.render_objects.values():
                if 'trail_buf' in obj and obj['trail_buf'] is not None:
                    obj['trail_buf'][:] = 0
                obj['trail_head'] = 0
                obj['trail_filled'] = False
                if obj.get('trail_line') is not None:
                    trail_colors = obj.get('trail_colors')
                    if trail_colors is not None:
                        obj['trail_line'].setData(
                            pos=np.zeros((1, 3), dtype=np.float32),
                            color=trail_colors[:1]
                        )

            self._update_orbits()
            self._apply_filter(self.txt_filter.text())
            if self.info_bubble_locked and self.selected_vessel is not None:
                projected = self._project_vessel(self.selected_vessel)
                if projected is not None:
                    self._show_info_bubble(self.selected_vessel, projected[0], projected[1])
            if self.conn:
                self.lbl_status.setText("Conectado  ●")
                self.lbl_status.setStyleSheet("color: #3fb950; font-size: 11px;")

        def _update_orbits(self):
            if not self.conn:
                return

            try:
                active_vids = set()
                theta = np.linspace(0, 2 * np.pi, ORBIT_POINTS)
                cos_t = np.cos(theta)
                sin_t = np.sin(theta)
                max_orbit_radius = KERBIN_RADIUS_KM

                vessels = self.conn.space_center.vessels

                for vessel in vessels:
                    try:
                        vid = vessel.name

                        if vid not in self.vessel_streams:
                            orb = vessel.orbit
                            self.vessel_streams[vid] = {
                                'situation':      self.conn.add_stream(getattr, vessel, 'situation'),
                                'sma':            self.conn.add_stream(getattr, orb, 'semi_major_axis'),
                                'inc':            self.conn.add_stream(getattr, orb, 'inclination'),
                                'lan':            self.conn.add_stream(getattr, orb, 'longitude_of_ascending_node'),
                                'argp':           self.conn.add_stream(getattr, orb, 'argument_of_periapsis'),
                                'ecc':            self.conn.add_stream(getattr, orb, 'eccentricity'),
                                'period':         self.conn.add_stream(getattr, orb, 'period'),
                                'true_anomaly':   self.conn.add_stream(getattr, orb, 'true_anomaly'),
                            }
                            try:
                                self.vessel_streams[vid]['orbital_speed'] = \
                                    self.conn.add_stream(getattr, vessel.flight(vessel.orbit.body.reference_frame), 'speed')
                            except Exception:
                                self.vessel_streams[vid]['orbital_speed'] = None

                        streams = self.vessel_streams[vid]
                        situation = streams['situation']()
                        sma = streams['sma']()

                        if situation.name not in ('orbiting', 'escaping') or sma <= 0:
                            continue

                        try:
                            if vessel.orbit.periapsis_altitude < 0:
                                continue
                        except Exception:
                            pass

                        active_vids.add(vid)

                        inc = streams['inc']()
                        lan = streams['lan']()
                        argp = streams['argp']()
                        ecc = streams['ecc']()
                        period = streams['period']()
                        r_orbit = sma / 1000.0
                        max_orbit_radius = max(max_orbit_radius, r_orbit * (1.0 + ecc))

                        if ecc < 0.999:
                            r_theta = r_orbit * (1 - ecc**2) / (1 + ecc * cos_t)
                        else:
                            r_theta = np.full_like(theta, r_orbit)

                        x_orb = r_theta * cos_t
                        y_orb = r_theta * sin_t
                        z_orb = np.zeros(ORBIT_POINTS)

                        ci, si_ = np.cos(inc), np.sin(inc)
                        cl, sl  = np.cos(lan), np.sin(lan)
                        ca, sa  = np.cos(argp), np.sin(argp)

                        R_inc = np.array([[1, 0, 0], [0, ci, -si_], [0, si_, ci]])
                        R_argp = np.array([[ca, -sa, 0], [sa, ca, 0], [0, 0, 1]])
                        R_lan = np.array([[cl, -sl, 0], [sl, cl, 0], [0, 0, 1]])
                        R = R_lan @ R_inc @ R_argp

                        orbital_coords = np.vstack((x_orb, y_orb, z_orb))
                        rotated = (R @ orbital_coords).T.astype(np.float32)

                        true_anom = streams['true_anomaly']()
                        r_now = r_orbit * (1 - ecc**2) / (1 + ecc * np.cos(true_anom))
                        x_now = r_now * np.cos(true_anom)
                        y_now = r_now * np.sin(true_anom)
                        pos_now = (R @ np.array([x_now, y_now, 0.0]))
                        sx, sy, sz = float(pos_now[0]), float(pos_now[1]), float(pos_now[2])

                        alt_km = r_now - KERBIN_RADIUS_KM

                        vel_ms = 0.0
                        try:
                            if streams['orbital_speed'] is not None:
                                vel_ms = streams['orbital_speed']()
                        except Exception:
                            pass

                        info_data = {
                            'alt_km': alt_km,
                            'period': period,
                            'inc': inc,
                            'ecc': ecc,
                            'vel_ms': vel_ms,
                        }

                        if vid not in self.render_objects:
                            cidx = self.color_counter % len(VESSEL_COLORS)
                            self.color_counter += 1
                            lc = VESSEL_COLORS[cidx]
                            dc = DOT_COLORS[cidx]

                            line = gl.GLLinePlotItem(
                                pos=rotated, color=ORBIT_LINE_COLOR,
                                width=1.5, antialias=True, mode='line_strip',
                                glOptions='opaque'
                            )
                            dot = gl.GLScatterPlotItem(
                                pos=np.array([[sx, sy, sz]], dtype=np.float32),
                                color=dc, size=8, pxMode=True, glOptions='opaque'
                            )

                            trail_buf = np.zeros((TRAIL_LEN, 3), dtype=np.float32)
                            trail_alphas = np.linspace(0.0, 1.0, TRAIL_LEN)
                            trail_colors = np.zeros((TRAIL_LEN, 4), dtype=np.float32)
                            trail_colors[:, 0] = lc[0]
                            trail_colors[:, 1] = lc[1]
                            trail_colors[:, 2] = lc[2]
                            trail_colors[:, 3] = trail_alphas
                            trail_line = gl.GLLinePlotItem(
                                pos=trail_buf, color=trail_colors,
                                width=2.0, antialias=True, mode='line_strip',
                                glOptions='translucent'
                            )

                            self.view.addItem(line)
                            self.view.addItem(dot)
                            self.view.addItem(trail_line)

                            card = VesselInfoCard(vid, lc)
                            card.clicked.connect(self._set_selected_vessel)
                            self.cards_layout.insertWidget(
                                self.cards_layout.count() - 1, card
                            )

                            self.render_objects[vid] = {
                                'line': line,
                                'orbit_pts': rotated,
                                'dot': dot,
                                'trail_line': trail_line,
                                'trail_buf': trail_buf,
                                'trail_head': 0,
                                'trail_filled': False,
                                'trail_colors': trail_colors,
                                'base_line_color': ORBIT_LINE_COLOR,
                                'base_dot_color': dc,
                                'pos_3d': (sx, sy, sz),
                                'info_data': info_data,
                                'color_idx': cidx,
                                'info_card': card,
                            }
                            card.update_data(alt_km, period, inc, ecc, vel_ms)
                        else:
                            obj = self.render_objects[vid]
                            obj['orbit_pts'] = rotated
                            obj['line'].setData(pos=rotated, color=obj['base_line_color'])
                            obj['dot'].setData(pos=np.array([[sx, sy, sz]], dtype=np.float32), color=obj['base_dot_color'])
                            obj['pos_3d'] = (sx, sy, sz)
                            obj['info_data'] = info_data

                            buf = obj['trail_buf']
                            head = obj['trail_head']
                            buf[head] = [sx, sy, sz]
                            obj['trail_head'] = (head + 1) % TRAIL_LEN
                            if not obj['trail_filled'] and head == TRAIL_LEN - 1:
                                obj['trail_filled'] = True

                            if obj['trail_filled']:
                                idx = obj['trail_head']
                                ordered = np.roll(buf, -idx, axis=0)
                            else:
                                ordered = buf[:head + 1]

                            if len(ordered) > 1:
                                tc = obj['trail_colors'][:len(ordered)]
                                obj['trail_line'].setData(pos=ordered, color=tc)

                            obj['info_card'].update_data(alt_km, period, inc, ecc, vel_ms)

                    except Exception:
                        continue

                if not self._camera_fitted and active_vids:
                    target_distance = max(5200.0, max_orbit_radius * 1.5)
                    self.view.setCameraPosition(distance=target_distance)
                    self._camera_fitted = True

                for vid in list(self.render_objects.keys()):
                    if vid not in active_vids:
                        obj = self.render_objects[vid]
                        for key in ('line', 'dot', 'trail_line'):
                            if obj.get(key) is not None:
                                try:
                                    self.view.removeItem(obj[key])
                                except Exception:
                                    pass
                        if obj.get('info_card') is not None:
                            obj['info_card'].deleteLater()
                        del self.render_objects[vid]
                        if self.selected_vessel == vid:
                            self.selected_vessel = None
                            self._hide_info_bubble()

                        if vid in self.vessel_streams:
                            for s in self.vessel_streams[vid].values():
                                try:
                                    if s is not None:
                                        s.remove()
                                except Exception:
                                    pass
                            del self.vessel_streams[vid]

            except Exception as e:
                self.timer.stop()
                self._clear_all_vessels()
                QMessageBox.warning(
                    self,
                    "Conexión perdida",
                    f"Se ha perdido la conexión con KSP.\nDetalle: {e}"
                )
                self.back_clicked.emit()

        def _mouse_press(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                hit = self._vessel_at_cursor(event)
                if hit is not None:
                    vid, px, py = hit
                    self.selected_vessel = vid
                    self.info_bubble_locked = True
                    self._show_info_bubble(vid, px, py)
                    self._update_selection_visuals()
                    self.is_rotating = False
                    return
                self.is_rotating = True
                self.last_mouse_pos = event.position()

        def _mouse_release(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                self.is_rotating = False

        def _wheel_event(self, event):
            delta = event.angleDelta().y()
            factor = 0.9 if delta > 0 else 1.1
            new_dist = self.view.opts['distance'] * factor
            new_dist = max(700, min(8000, new_dist))
            self.view.setCameraPosition(distance=new_dist)
            self.view.update()

        def _mouse_move(self, event):
            if self.is_rotating and self.last_mouse_pos is not None:
                delta = event.position() - self.last_mouse_pos
                self.last_mouse_pos = event.position()
                sens = 0.18
                new_azim = self.view.opts['azimuth'] - delta.x() * sens
                new_elev = self.view.opts['elevation'] + delta.y() * sens
                new_elev = max(-89.0, min(89.0, new_elev))
                self.view.setCameraPosition(azimuth=new_azim, elevation=new_elev)
                self.view.update()
                if self.info_bubble_locked and self.selected_vessel is not None:
                    projected = self._project_vessel(self.selected_vessel)
                    if projected is not None:
                        self._show_info_bubble(self.selected_vessel, projected[0], projected[1])
                return

            if self.info_bubble_locked:
                return

            hit = self._vessel_at_cursor(event)
            if hit is not None:
                vid, px, py = hit
                self.hovered_vessel = vid
                self._show_info_bubble(vid, px, py)
            else:
                if self.info_bubble is not None:
                    self.info_bubble.hide()
                self.hovered_vessel = None

        def resizeEvent(self, event):
            super().resizeEvent(event)
            self._reposition_back_button()

        def showEvent(self, event):
            super().showEvent(event)
            self._reposition_back_button()
            if hasattr(self, 'btn_back'):
                self.btn_back.raise_()

        def _reposition_back_button(self):
            if hasattr(self, 'btn_back') and self.btn_back is not None:
                self.btn_back.adjustSize()
                w = max(self.btn_back.width(), 90)
                h = self.btn_back.height()
                self.btn_back.setFixedSize(w, h)
                self.btn_back.move(self.width() - w - 24, self.height() - h - 20)
                self.btn_back.raise_()

else:
    # Fallbacks si no están disponibles las dependencias
    class ConnectThread(QThread):  # type: ignore
        pass

    def connect_to_ksp_async(on_success, on_failure):  # type: ignore
        return None

    class KSPRealTimeVisualizer(QWidget):  # type: ignore
        back_clicked = pyqtSignal()
        def __init__(self, conn=None, parent=None):
            super().__init__(parent)
            self.timer = QTimer(self)
        def set_connection(self, conn):
            pass
        def _clear_all_vessels(self):
            pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.auth = AuthManager()
        self.setWindowTitle(APP_NAME)
        self.resize(1120, 720)
        self.setMinimumSize(900, 620)

        # Estado de la conexión KSP (establecida durante la pantalla de carga)
        self._ksp_conn = None
        self._ksp_error: str | None = None
        self._ksp_thread = None   # Referencia al QThread para evitar GC prematuro

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.login = LoginScreen(self.auth, self.show_startup_loading)
        self.startup = StartupLoadingScreen(
            on_finished=self.show_command_center,
            ksp_callbacks=(self._on_ksp_connected, self._on_ksp_failed),
        )
        self.command = CommandCenter(self.prepare_module)
        self.transition = ModuleTransitionScreen()

        self.stack.addWidget(self.login)
        self.stack.addWidget(self.startup)
        self.stack.addWidget(self.command)
        self.stack.addWidget(self.transition)

        # Instanciar el visualizador orbital e integrarlo en la pila de vistas
        self.visualizer = KSPRealTimeVisualizer(conn=self._ksp_conn)
        self.stack.addWidget(self.visualizer)
        self.visualizer.back_clicked.connect(self.show_command_center)

    # ── Callbacks de conexión KSP ──────────────────────────────────────────────

    def _on_ksp_connected(self, conn) -> None:
        """Recibe la conexión KSP establecida desde el hilo de background."""
        self._ksp_conn = conn
        self._ksp_error = None
        if self.visualizer is not None:
            self.visualizer.set_connection(conn)

    def _on_ksp_failed(self, err: str) -> None:
        """Registra el error de conexión KSP; se informará al usuario si pulsa el módulo."""
        self._ksp_conn = None
        self._ksp_error = err

    # ── Navegación entre pantallas ─────────────────────────────────────────────

    def show_startup_loading(self) -> None:
        self.stack.setCurrentWidget(self.startup)
        # Diferir el inicio para que Qt tenga tiempo de pintar la pantalla de carga
        # antes de arrancar los timers y la conexión KSP en background.
        QTimer.singleShot(50, self.startup.start)

    def show_command_center(self) -> None:
        self.stack.setCurrentWidget(self.command)
        fade_in(self.command, 650)

    def prepare_module(self, module_name: str) -> None:
        target = MODULES.get(module_name)
        if not target:
            QMessageBox.information(self, APP_NAME, "Módulo no disponible actualmente.")
            return

        # El módulo "Mapa orbital" se abre dentro del mismo proceso y ventana
        if module_name == "Mapa orbital":
            fade_out(self.command, lambda: self._show_transition(module_name, target))
            return

        # Otros módulos: lanzar como proceso externo (comportamiento original)
        target_path = BASE_DIR / target
        if not target_path.exists():
            QMessageBox.warning(self, APP_NAME, f"No se encontró el módulo: {target}")
            return
        fade_out(self.command, lambda: self._show_transition(module_name, target))

    def _show_transition(self, module_name: str, target: str) -> None:
        self.stack.setCurrentWidget(self.transition)
        self.transition.start(module_name, target, self.launch_module)

    def launch_module(self, module_name: str, target: str) -> None:
        """Abre el módulo: el mapa orbital dentro del proceso; el resto como proceso externo."""
        if module_name == "Mapa orbital":
            self._launch_orbital_map()
            return

        # Módulos externos (comportamiento original)
        module_path = BASE_DIR / target
        try:
            subprocess.Popen([sys.executable, str(module_path)], cwd=str(BASE_DIR))
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"No se pudo abrir {module_name}: {exc}")
            self.show_command_center()
            return
        self.statusBar().showMessage(f"{module_name} iniciado", 5000)
        self.showMinimized()

    def _launch_orbital_map(self) -> None:
        """Abre KSPRealTimeVisualizer en el mismo proceso, reutilizando la conexión KSP."""
        if not _KSP_AVAILABLE or self.visualizer is None:
            QMessageBox.critical(
                self,
                APP_NAME,
                "El módulo orbital no está disponible.\n"
                "Asegúrate de tener instalados: krpc, pyqtgraph, numpy.",
            )
            self.show_command_center()
            return

        if self._ksp_conn is None:
            # Conexión aún en progreso o fallida
            if self._ksp_error:
                detalle = f"\n\nDetalle: {self._ksp_error}"
            else:
                detalle = "\n\nLa conexión sigue en progreso. Espera unos segundos e inténtalo de nuevo."
            QMessageBox.warning(
                self,
                APP_NAME,
                f"No se pudo conectar con KSP.{detalle}",
            )
            self.show_command_center()
            return

        # Pasar conexión al visualizador, iniciar su actualización y transicionar a la pantalla del visualizador
        self.visualizer.set_connection(self._ksp_conn)
        self.stack.setCurrentWidget(self.visualizer)
        fade_in(self.visualizer, 650)
        self.statusBar().showMessage("Mapa orbital iniciado", 5000)

    def closeEvent(self, event) -> None:
        """Asegura detener hilos y conexiones al cerrar la aplicación principal."""
        if _KSP_AVAILABLE and hasattr(self, 'visualizer') and self.visualizer is not None:
            self.visualizer.timer.stop()
            self.visualizer._clear_all_vessels()
            if self.visualizer.conn:
                try:
                    self.visualizer.conn.close()
                except Exception:
                    pass
        event.accept()


def build_stylesheet() -> str:
    return """
    QWidget {
        background: #07111d;
        color: #e6eef7;
        font-family: "Segoe UI", "Inter", Arial, sans-serif;
        font-size: 14px;
    }
    QMainWindow {
        background: #07111d;
    }
    /* Forzar que las etiquetas y textos sean transparentes */
    QLabel {
        background: transparent;
    }
    #glassPanel {
        background-color: rgba(18, 31, 47, 220);
        border: 1px solid rgba(126, 164, 196, 80);
        border-radius: 14px;
    }
    #title {
        color: #f3f8fc;
        font-size: 24px;
        font-weight: 700;
    }
    #transitionTitle {
        color: #eef7fb;
        font-size: 22px;
        font-weight: 700;
    }
    #muted {
        color: #91a8bb;
        font-size: 13px;
    }
    #status {
        color: #9fc7dc;
        font-size: 15px;
    }
    #error {
        color: #ff8f8f;
        min-height: 22px;
    }
    QLineEdit {
        background: rgba(9, 20, 32, 210);
        color: #eef7fb;
        border: 1px solid rgba(126, 164, 196, 90);
        border-radius: 9px;
        padding: 12px 14px;
        selection-background-color: #2e83a6;
    }
    QLineEdit:focus {
        border: 1px solid #75c4e7;
        background: rgba(13, 28, 43, 235);
    }
    QPushButton#primaryButton {
        background: #1d6f91;
        color: #f3fbff;
        border: 1px solid #66c7e8;
        border-radius: 9px;
        padding: 12px 16px;
        font-weight: 700;
    }
    QPushButton#primaryButton:hover {
        background: #2585aa;
        border-color: #9ee4f5;
    }
    QPushButton#moduleCard {
        text-align: left;
        background: rgba(15, 29, 43, 230);
        color: #eef7fb;
        border: 1px solid rgba(120, 162, 190, 90);
        border-left: 4px solid #6fc4e9;
        border-radius: 10px;
        padding: 20px 22px;
        font-size: 18px;
        font-weight: 700;
    }
    QPushButton#moduleCard:hover {
        background: rgba(24, 47, 66, 245);
        border-color: rgba(150, 222, 241, 180);
    }
    QPushButton#moduleCardDisabled {
        text-align: left;
        background: rgba(12, 22, 32, 180);
        color: #6f8291;
        border: 1px solid rgba(100, 126, 147, 55);
        border-left: 4px solid #405466;
        border-radius: 10px;
        padding: 20px 22px;
        font-size: 18px;
        font-weight: 700;
    }
    #stateChip {
        color: #aef4df;
        background: rgba(28, 98, 83, 120);
        border: 1px solid rgba(133, 229, 202, 120);
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 12px;
        font-weight: 700;
    }
    QMessageBox {
        background: #101d2c;
    }
    """


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(build_stylesheet())

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())