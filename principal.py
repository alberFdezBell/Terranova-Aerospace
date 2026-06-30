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
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QPalette, QFont, QCursor, QVector3D
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
            _set(self.lbl_vel,    "Velocidad",   f"{vel_ms:.0f} m/s")

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
            self._press_pos = None

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
                    background: transparent;
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
                    background: rgba(13,17,23,200);
                    border: 1px solid #30363d;
                    color: #c9d1d9;
                    font-size: 13px;
                    font-weight: bold;
                    border-radius: 6px;
                    padding: 6px 14px;
                }
                QPushButton#btnBack:hover {
                    background: rgba(30,40,55,220);
                    border-color: #58a6ff;
                    color: #58a6ff;
                }
                QPushButton#btnBack:pressed {
                    background: rgba(13,17,23,240);
                    color: #1f6feb;
                }
                QLineEdit {
                    background: rgba(13,17,23,210);
                    color: #c9d1d9;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    padding: 7px 10px;
                    font-size: 12px;
                }
                QLineEdit:focus { border-color: #58a6ff; }
                QScrollBar:vertical {
                    background: rgba(22,27,34,180); width: 5px; border-radius: 3px;
                }
                QScrollBar::handle:vertical {
                    background: #30363d; border-radius: 3px;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            """)

        def _build_ui(self):
            import os
            from PyQt6.QtGui import QPixmap

            # El mapa ocupa TODA la pantalla
            root_layout = QVBoxLayout(self)
            root_layout.setContentsMargins(0, 0, 0, 0)
            root_layout.setSpacing(0)

            # Vista 3D a pantalla completa
            self.view = gl.GLViewWidget(self)
            self.view.setBackgroundColor('#0d1117')
            self.view.setCameraPosition(distance=5200, elevation=22, azimuth=-45)
            self.view.setMouseTracking(True)
            root_layout.addWidget(self.view)

            # Info bubble (tooltip flotante sobre el mapa)
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

            # ── Overlay panel (sobre el mapa, esquina superior-izquierda) ──────
            self.overlay = QWidget(self)
            self.overlay.setFixedWidth(260)
            self.overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            overlay_layout = QVBoxLayout(self.overlay)
            overlay_layout.setContentsMargins(12, 14, 12, 14)
            overlay_layout.setSpacing(8)

            # Logo
            logo_lbl = QLabel()
            ruta_imagen = os.path.join(os.path.dirname(__file__), "icons", "tas_cortado.png")
            px = QPixmap(ruta_imagen)
            if not px.isNull():
                px = px.scaledToWidth(236, Qt.TransformationMode.SmoothTransformation)
                logo_lbl.setPixmap(px)
                logo_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            else:
                logo_lbl.setText("Terranova Aerospace")
                logo_lbl.setStyleSheet("color:#dce9f6; font-size:14px; font-weight:700;")
            overlay_layout.addWidget(logo_lbl)

            # Buscador
            self.txt_filter = QLineEdit()
            self.txt_filter.setPlaceholderText("Buscar objeto…")
            self.txt_filter.setClearButtonEnabled(True)
            self.txt_filter.textChanged.connect(self._apply_filter)
            self.txt_filter.setStyleSheet("""
                QLineEdit {
                    background: rgba(13,17,23,210);
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    color: #c9d1d9;
                    padding: 7px 10px;
                    font-size: 12px;
                }
                QLineEdit:focus { border-color: #58a6ff; }
            """)
            overlay_layout.addWidget(self.txt_filter)

            # Contenedor animado de resultados
            self.results_widget = QWidget()
            self.results_widget.setStyleSheet("background: transparent;")
            self.results_layout = QVBoxLayout(self.results_widget)
            self.results_layout.setContentsMargins(0, 2, 0, 2)
            self.results_layout.setSpacing(2)
            self.results_widget.setMaximumHeight(0)   # Oculto inicialmente
            overlay_layout.addWidget(self.results_widget)

            # Panel de información del satélite seleccionado
            self.info_panel = QFrame()
            self.info_panel.setStyleSheet("""
                QFrame {
                    background: rgba(13,17,23,210);
                    border: 1px solid #30363d;
                    border-radius: 8px;
                }
            """)
            info_layout = QVBoxLayout(self.info_panel)
            info_layout.setContentsMargins(10, 10, 10, 10)
            info_layout.setSpacing(5)

            self.info_title = QLabel("")
            self.info_title.setStyleSheet("color:#e6edf3; font-weight:bold; font-size:12px; background:transparent;")
            self.info_title.setTextFormat(Qt.TextFormat.RichText)
            info_layout.addWidget(self.info_title)

            self.info_body = QLabel("")
            self.info_body.setStyleSheet("color:#c9d1d9; font-size:11px; background:transparent; line-height:160%;")
            self.info_body.setTextFormat(Qt.TextFormat.RichText)
            self.info_body.setWordWrap(True)
            info_layout.addWidget(self.info_body)

            self.btn_close_result = QPushButton("Cerrar resultado")
            self.btn_close_result.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_close_result.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #6e7681;
                    border: 1px solid #30363d;
                    border-radius: 5px;
                    padding: 4px 10px;
                    font-size: 11px;
                    margin-top: 4px;
                }
                QPushButton:hover {
                    color: #c9d1d9;
                    border-color: #58a6ff;
                }
                QPushButton:pressed {
                    color: #8b949e;
                }
            """)
            self.btn_close_result.clicked.connect(self._deselect_vessel)
            info_layout.addWidget(self.btn_close_result)

            self.info_panel.hide()
            overlay_layout.addWidget(self.info_panel)

            overlay_layout.addStretch()

            # Dummy widgets para compatibilidad interna (no visibles)
            self.btn_connect    = QPushButton()
            self.btn_connect.clicked.connect(self._connect_to_ksp)
            self.btn_disconnect = QPushButton()
            self.btn_disconnect.clicked.connect(self._disconnect)
            self.btn_reload     = QPushButton()
            self.btn_reload.clicked.connect(self._on_reload_clicked)
            self.lbl_status     = QLabel()

            # Botón "← Volver" flotante en esquina inferior-izquierda
            self.btn_back = QPushButton("← Volver", self)
            self.btn_back.setObjectName("btnBack")
            self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_back.clicked.connect(self._on_back_clicked)
            self.btn_back.adjustSize()
            self.btn_back.show()
            self.btn_back.raise_()

            # Animación de altura para el contenedor de resultados
            self._results_anim = QPropertyAnimation(self.results_widget, b"maximumHeight")
            self._results_anim.setDuration(220)
            self._results_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            # Conectar eventos del mapa
            self.view.mouseMoveEvent    = self._mouse_move
            self.view.mousePressEvent   = self._mouse_press
            self.view.mouseReleaseEvent = self._mouse_release
            self.view.wheelEvent        = self._wheel_event

            

        def _make_separator(self) -> QFrame:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("color: #21262d; margin: 2px 0;")
            return sep

        # ── Resultados de búsqueda animados ───────────────────────────────────

        def _rebuild_results(self):
            """Reconstruye la lista de resultados según el filtro activo."""
            # Limpiar resultados anteriores
            while self.results_layout.count():
                item = self.results_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()

            text = self.active_filter_text
            if not text:
                self._animate_results(0)
                return

            matches = [
                vid for vid in self.render_objects
                if text in vid.lower()
            ]

            if not matches:
                no_res = QLabel("Sin resultados")
                no_res.setStyleSheet("color:#6e7681; font-size:11px; padding:4px 6px; background:transparent;")
                self.results_layout.addWidget(no_res)
                self._animate_results(32)
                return

            for vid in matches:
                btn = QPushButton(f"🛰  {vid}")
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(13,17,23,210);
                        color: #c9d1d9;
                        border: 1px solid #30363d;
                        border-left: 3px solid #58a6ff;
                        border-radius: 5px;
                        padding: 6px 10px;
                        text-align: left;
                        font-size: 11px;
                    }
                    QPushButton:hover {
                        background: rgba(30,40,60,240);
                        border-color: #58a6ff;
                        color: #e6edf3;
                    }
                    QPushButton:pressed {
                        background: rgba(10,15,25,240);
                    }
                """)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda checked=False, v=vid: self._select_vessel(v))
                self.results_layout.addWidget(btn)

            target_h = min(len(matches) * 38, 240)
            self._animate_results(target_h)

        def _animate_results(self, target_h: int):
            self._results_anim.stop()
            self._results_anim.setStartValue(self.results_widget.maximumHeight())
            self._results_anim.setEndValue(target_h)
            self._results_anim.start()

        def _select_vessel(self, vessel_name: str):
            """Selecciona un satélite: muestra info, oculta resultados, hace zoom."""
            if vessel_name not in self.render_objects:
                return
            self.selected_vessel = vessel_name
            # Limpiar búsqueda y cerrar resultados
            self.txt_filter.blockSignals(True)
            self.txt_filter.clear()
            self.txt_filter.blockSignals(False)
            self.active_filter_text = ""
            self._animate_results(0)

            self._update_selection_visuals()
            self._update_info_panel(vessel_name)
            self.info_panel.show()

            # Zoom y seguimiento de cámara inicial (reinicia ángulos y zoom)
            self._focus_camera_on(vessel_name, initial=True)

        def _animate_camera_to(self, target_pos, target_dist, target_azim, target_elev, duration=900):
            from PyQt6.QtCore import QVariantAnimation, QEasingCurve
            
            if hasattr(self, '_camera_anim_obj') and self._camera_anim_obj is not None:
                self._camera_anim_obj.stop()
                
            start_pos = self.view.opts['center']
            start_dist = self.view.opts['distance']
            start_azim = self.view.opts['azimuth']
            start_elev = self.view.opts['elevation']
            
            if not isinstance(start_pos, QVector3D):
                start_pos = QVector3D(0, 0, 0)
                
            anim = QVariantAnimation(self)
            anim.setDuration(duration)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            
            azim_diff = target_azim - start_azim
            azim_diff = (azim_diff + 180) % 360 - 180
            
            def update_cam(t_val):
                curr_pos = start_pos + (target_pos - start_pos) * t_val
                curr_dist = start_dist + (target_dist - start_dist) * t_val
                curr_azim = start_azim + azim_diff * t_val
                curr_elev = start_elev + (target_elev - start_elev) * t_val
                self.view.setCameraPosition(pos=curr_pos, distance=curr_dist, azimuth=curr_azim, elevation=curr_elev)
                self.view.update()
                
            anim.valueChanged.connect(update_cam)
            self._camera_anim_obj = anim
            anim.start()

        def _focus_camera_on(self, vessel_name: str, initial: bool = False):
            """Centra la cámara en el satélite seleccionado. Preserva zoom y rotación a menos que initial=True."""
            obj = self.render_objects.get(vessel_name)
            if obj is None or 'pos_3d' not in obj:
                return
            sx, sy, sz = obj['pos_3d']
            pos = QVector3D(sx, sy, sz)
            if initial:
                dist = max(800.0, math.hypot(math.hypot(sx, sy), sz) * 1.8)
                dist = min(dist, 4000.0)
                # Calcular azimut y elevación para apuntar a la posición
                azim = math.degrees(math.atan2(sy, sx))
                elev = math.degrees(math.atan2(sz, math.hypot(sx, sy)))
                self._animate_camera_to(pos, dist, azim, elev, duration=900)
            else:
                anim_running = (
                    hasattr(self, '_camera_anim_obj') and 
                    self._camera_anim_obj is not None and 
                    self._camera_anim_obj.state() == QVariantAnimation.State.Running
                )
                if not anim_running:
                    self.view.setCameraPosition(pos=pos)
                    self.view.update()

        def _update_info_panel(self, vessel_name: str):
            """Rellena el panel con los datos del satélite en texto limpio."""
            obj = self.render_objects.get(vessel_name, {})
            info = obj.get('info_data', {})
            cidx = obj.get('color_idx', 0)
            color = DOT_COLORS[cidx % len(DOT_COLORS)]
            color_hex = "#{:02X}{:02X}{:02X}".format(
                int(color[0]*255), int(color[1]*255), int(color[2]*255)
            )
            self.info_title.setText(
                f"<span style='color:{color_hex}'>🛰 {vessel_name}</span>"
            )

            alt_km  = info.get('alt_km', 0)
            period  = info.get('period', 0)
            inc_rad = info.get('inc', 0)
            ecc     = info.get('ecc', 0)
            vel_ms  = info.get('vel_ms', 0)

            c_key = "#6e7681"   # color etiqueta
            c_val = "#e6edf3"   # color valor
            self.info_body.setText(
                f"<span style='color:{c_key}'>Altitud</span>  "
                f"<span style='color:{c_val}'>{alt_km:,.0f} km</span><br>"
                f"<span style='color:{c_key}'>Período</span>  "
                f"<span style='color:{c_val}'>{VesselInfoCard._fmt_time(period)}</span><br>"
                f"<span style='color:{c_key}'>Inclinación</span>  "
                f"<span style='color:{c_val}'>{math.degrees(inc_rad):.2f}°</span><br>"
                f"<span style='color:{c_key}'>Excentricidad</span>  "
                f"<span style='color:{c_val}'>{ecc:.4f}</span><br>"
                f"<span style='color:{c_key}'>Velocidad</span>  "
                f"<span style='color:{c_val}'>{vel_ms:,.0f} m/s</span>"
            )

        def _deselect_vessel(self):
            """Cierra el panel de info y restaura la vista general fluidamente."""
            self.selected_vessel = None
            self.info_panel.hide()
            self._hide_info_bubble()
            self._update_selection_visuals()
            self._animate_camera_to(QVector3D(0, 0, 0), 5200.0, -45.0, 22.0, duration=900)

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
            self.connect_thread = ConnectThread()
            self.connect_thread.success.connect(self._on_connected)
            self.connect_thread.failure.connect(self._on_connect_failed)
            self.connect_thread.start()

        def _on_connected(self, conn):
            self.conn = conn
            self._camera_fitted = False
            self._reload_data()
            self.timer.start(3000)

        def _on_connect_failed(self, err: str):
            pass  # Sin UI de estado visible

        def _disconnect(self):
            self.timer.stop()
            self._clear_all_vessels()

            if self.conn:
                try:
                    self.conn.close()
                except Exception:
                    pass
                self.conn = None

            self._camera_fitted = False

        def _clear_all_vessels(self):
            for vid, obj in self.render_objects.items():
                for key in ('line', 'dot', 'trail_line'):
                    if key in obj and obj[key] is not None:
                        try:
                            self.view.removeItem(obj[key])
                        except Exception:
                            pass

            self.render_objects.clear()

            for vid, streams in self.vessel_streams.items():
                for s in streams.values():
                    try:
                        if s is not None:
                            s.remove()
                    except Exception:
                        pass
            self.vessel_streams.clear()
            self.color_counter = 0
            self._camera_fitted = False
            self.active_filter_text = ""
            self.selected_vessel = None
            if hasattr(self, 'info_panel'):
                self.info_panel.hide()
            self._hide_info_bubble()

        def _on_back_clicked(self):
            self.timer.stop()
            self.back_clicked.emit()

        def _set_selected_vessel(self, vessel_name: str):
            """Redirige a _select_vessel para compatibilidad."""
            self._select_vessel(vessel_name)

        def _project_point(self, point_3d):
            vw = self.view.width()
            vh = self.view.height()
            if vw <= 0 or vh <= 0:
                return None

            try:
                r = self.view.getViewport()
                proj = self.view.projectionMatrix(r, r)
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
            cidx = obj.get('color_idx', 0)
            color = DOT_COLORS[cidx % len(DOT_COLORS)]
            color_hex = "#{:02X}{:02X}{:02X}".format(
                int(color[0] * 255),
                int(color[1] * 255),
                int(color[2] * 255)
            )
            return f"<b style='color:{color_hex}'>🛰 {vessel_name}</b>"

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
            self._reload_data()

        def _update_selection_visuals(self):
            if self.selected_vessel is not None and self.selected_vessel not in self.render_objects:
                self.selected_vessel = None

            # Detectar si hay un satélite bajo el cursor
            has_hover = self.hovered_vessel is not None and self.selected_vessel is None

            for vid, obj in self.render_objects.items():
                is_selected = self.selected_vessel == vid
                is_hovered = self.hovered_vessel == vid
                show_in_map = self.selected_vessel is None or is_selected

                line = obj.get('line')
                dot = obj.get('dot')
                trail = obj.get('trail_line')

                # Calcular colores según hover y selección
                if has_hover:
                    if is_hovered:
                        line_color = obj.get('base_line_color', ORBIT_LINE_COLOR)
                        dot_color = obj.get('base_dot_color')
                        trail_visible = True
                    else:
                        line_color = (0.05, 0.2, 0.25, 0.15)  # Cian atenuado con baja opacidad
                        base_dot = obj.get('base_dot_color')
                        if base_dot is not None:
                            dot_color = (base_dot[0]*0.2, base_dot[1]*0.2, base_dot[2]*0.2, 0.25)
                        else:
                            dot_color = (0.2, 0.2, 0.2, 0.2)
                        trail_visible = False  # Ocultar rastro para limpiar la escena
                else:
                    line_color = obj.get('base_line_color', ORBIT_LINE_COLOR)
                    dot_color = obj.get('base_dot_color')
                    trail_visible = show_in_map

                if line is not None:
                    line.setVisible(show_in_map)
                    if show_in_map and line_color is not None:
                        line.setData(pos=obj['orbit_pts'], color=line_color)

                if dot is not None:
                    dot.setVisible(show_in_map)
                    if show_in_map and dot_color is not None:
                        dot.setData(pos=np.array([obj['pos_3d']], dtype=np.float32), color=dot_color)

                if trail is not None:
                    trail.setVisible(trail_visible)
                    if trail_visible:
                        trail_colors = obj.get('trail_colors')
                        ordered = obj.get('ordered_trail')
                        if trail_colors is not None and ordered is not None:
                            trail.setData(pos=ordered, color=trail_colors)

        def _apply_filter(self, text: str):
            self.active_filter_text = (text or "").strip().lower()
            # Si hay texto activo, deseleccionar y ocultar info panel
            if self.active_filter_text:
                if self.selected_vessel is not None:
                    self.selected_vessel = None
                    self.info_panel.hide()
                    self._hide_info_bubble()
                    self._update_selection_visuals()
            else:
                # Campo vacío: colapsar resultados sin deselectar
                self._animate_results(0)
                return
            self._rebuild_results()

        def _reload_data(self):
            if not self.conn:
                return

            for obj in self.render_objects.values():
                if 'trail_buf' in obj and obj['trail_buf'] is not None and 'pos_3d' in obj:
                    sx, sy, sz = obj['pos_3d']
                    obj['trail_buf'][:, 0] = sx
                    obj['trail_buf'][:, 1] = sy
                    obj['trail_buf'][:, 2] = sz
                    obj['ordered_trail'] = obj['trail_buf'].copy()
                obj['trail_head'] = 0
                obj['trail_filled'] = False
                if obj.get('trail_line') is not None:
                    trail_colors = obj.get('trail_colors')
                    ordered = obj.get('ordered_trail')
                    if trail_colors is not None and ordered is not None:
                        obj['trail_line'].setData(
                            pos=ordered[:1],
                            color=trail_colors[:1]
                        )

            self._update_orbits()
            # Refrescar panel de info si hay selección activa (no reinicia la orientación)
            if self.selected_vessel is not None and self.selected_vessel in self.render_objects:
                self._update_info_panel(self.selected_vessel)
                self._focus_camera_on(self.selected_vessel, initial=False)

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
                            # Velocidad orbital directa desde el objeto orbit (evita el bug de 0 m/s)
                            try:
                                self.vessel_streams[vid]['orbital_speed'] = \
                                    self.conn.add_stream(getattr, vessel.orbit, 'speed')
                            except Exception:
                                try:
                                    self.vessel_streams[vid]['orbital_speed'] = \
                                        self.conn.add_stream(getattr, vessel.flight(vessel.orbit.body.non_rotating_reference_frame), 'speed')
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

                            # Inicializar el buffer de rastro con la posición inicial del satélite (evita líneas al origen)
                            trail_buf = np.empty((TRAIL_LEN, 3), dtype=np.float32)
                            trail_buf[:, 0] = sx
                            trail_buf[:, 1] = sy
                            trail_buf[:, 2] = sz

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
                                'ordered_trail': trail_buf.copy(),
                            }
                        else:
                            obj = self.render_objects[vid]
                            obj['orbit_pts'] = rotated
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
                                # Solo usar los slots que han sido escritos, el resto queda en la posición inicial del satélite (sin línea al origen)
                                ordered = buf[:head + 1] if head > 0 else buf[:1]

                            obj['ordered_trail'] = ordered

                            # Actualizar panel de info si este satélite está seleccionado
                            if self.selected_vessel == vid:
                                self._update_info_panel(vid)
                                self._focus_camera_on(vid, initial=False)

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
                        del self.render_objects[vid]
                        if self.selected_vessel == vid:
                            self.selected_vessel = None
                            self.info_panel.hide()
                            self._hide_info_bubble()

                        if vid in self.vessel_streams:
                            for s in self.vessel_streams[vid].values():
                                try:
                                    if s is not None:
                                        s.remove()
                                except Exception:
                                    pass
                            del self.vessel_streams[vid]

                # Aplicar colores y visibilidad correctos (respeta hover y selección)
                self._update_selection_visuals()

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
                    self._select_vessel(vid)
                    self.is_rotating = False
                    self._press_pos = None   # no deseleccionar en release
                    return
                # Guardar posición del press para distinguir click de drag
                self._press_pos = event.position()
                self.is_rotating = True
                self.last_mouse_pos = event.position()

        def _mouse_release(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                self.is_rotating = False
                # Solo deseleccionar si fue un click puro (sin arrastre)
                if self._press_pos is not None and self.selected_vessel is not None:
                    delta = event.position() - self._press_pos
                    if (delta.x() ** 2 + delta.y() ** 2) < 16:  # < 4px de movimiento
                        self._deselect_vessel()
                self._press_pos = None

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
                return

            hit = self._vessel_at_cursor(event)
            if hit is not None:
                vid, px, py = hit
                if self.hovered_vessel != vid:
                    self.hovered_vessel = vid
                    self._show_info_bubble(vid, event.position().x(), event.position().y())
                    self._update_selection_visuals()
                else:
                    self._show_info_bubble(vid, event.position().x(), event.position().y())
            else:
                if self.hovered_vessel is not None:
                    self.hovered_vessel = None
                    if self.info_bubble is not None:
                        self.info_bubble.hide()
                    self._update_selection_visuals()
                else:
                    if self.info_bubble is not None:
                        self.info_bubble.hide()

        def resizeEvent(self, event):
            super().resizeEvent(event)
            self._reposition_overlay()
            self._reposition_back_button()

        def showEvent(self, event):
            super().showEvent(event)
            self._reposition_overlay()
            self._reposition_back_button()
            if hasattr(self, 'btn_back'):
                self.btn_back.raise_()

        def _reposition_overlay(self):
            if hasattr(self, 'overlay') and self.overlay is not None:
                h = self.height() if self.height() > 0 else 800
                self.overlay.setGeometry(0, 0, 260, h)
                self.overlay.raise_()

        def _reposition_back_button(self):
            if hasattr(self, 'btn_back') and self.btn_back is not None:
                self.btn_back.adjustSize()
                w = max(self.btn_back.width(), 1)
                h = self.btn_back.height()
                self.btn_back.setFixedSize(w, h)
                
                # --- NUEVO: Estilo transparente con subrayado al pasar el cursor ---
                self.btn_back.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        border: none;
                        color: #FFFFFF; /* Cambia el color del texto si lo necesitas */
                        text-decoration: none;
                    }
                    QPushButton:hover {
                        text-decoration: underline;
                    }
                """)
                # -----------------------------------------------------------------

                # Posición: esquina inferior-izquierda
                self.btn_back.move(16, self.height() - h - 16)
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