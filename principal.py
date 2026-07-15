"""
Terranova Aerospace command center.

Entry point for authentication, startup loading, command navigation, and
internal/external module launching.
"""

from __future__ import annotations

import base64
import html
import hashlib
import hmac
import json
import math
import mimetypes
import os
import random
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from PyQt6.QtCore import QPointF
from PyQt6.QtCore import QPoint, QRectF, QEvent
from PyQt6.QtCore import QByteArray, QBuffer
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtCore import QVariantAnimation

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QSize, Qt, QTimer, QThread, pyqtSignal, pyqtProperty, QDate
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap, QPalette, QFont, QCursor, QVector3D, QFontMetrics, QBrush, QTextCursor, QTextDocument
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QHeaderView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QSizePolicy,
    QDateEdit,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTextBrowser,
    QStackedWidget,
    QMenu,
    QToolButton,
    QRubberBand,
    QVBoxLayout,
    QWidget,
)

try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    _MULTIMEDIA_AVAILABLE = True
except Exception:
    QAudioOutput = None  # type: ignore
    QMediaPlayer = None  # type: ignore
    QVideoWidget = None  # type: ignore
    _MULTIMEDIA_AVAILABLE = False

try:
    from PyQt6.QtPdf import QPdfDocument
    from PyQt6.QtPdfWidgets import QPdfView
    _PDF_AVAILABLE = True
except Exception:
    QPdfDocument = None  # type: ignore
    QPdfView = None  # type: ignore
    _PDF_AVAILABLE = False

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
PANEL_IMAGE_DIR = BASE_DIR / "icons" / "panel"

HASH_ITERATIONS = 240_000

MODULES: dict[str, str | None] = {
    "Mapa orbital": "internal",
    "Notas de prensa": "internal",
    "Lista de satélites": "internal",
    "Programación": None,
    "Centro de mando": None,
    "Personal": None,
}

MODULE_PANEL_IMAGES: dict[str, str] = {
    "Mapa orbital": "1.png",
    "Notas de prensa": "2.png",
    "Lista de satélites": "3.png",
    "Programación": "4.png",
    "Centro de mando": "5.png",
    "Personal": "6.png",
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
    "Cargando lista de satélites...",
    "Sincronizando satélites...",
    "Estableciendo conexión...",
    "Validando subsistemas...",
    "Transferencia de control en curso...",
]

SATELLITES_FILE = CONFIG_DIR / "satellites.dat"
SATELLITES_GROUPS_FILE = CONFIG_DIR / "satellite_groups.dat"
SATELLITES_GAMES_FILE = CONFIG_DIR / "satellite_games.dat"
SATELLITES_MEDIA_DIR = CONFIG_DIR / "satellite_media"
PRESS_DIR = CONFIG_DIR / "press"
PRESS_FILE = PRESS_DIR / "notes.json"
PRESS_MEDIA_DIR = PRESS_DIR / "media"
PRESS_MEDIA_IMAGES_DIR = PRESS_MEDIA_DIR / "images"
PRESS_MEDIA_VIDEOS_DIR = PRESS_MEDIA_DIR / "videos"
PRESS_MEDIA_DOCUMENTS_DIR = PRESS_MEDIA_DIR / "documents"
KSP_USER_DIR = Path(os.environ.get("USERPROFILE", "")) / "AppData" / "LocalLow" / "Squad" / "Kerbal Space Program"
KSP_PLAYER_LOG = KSP_USER_DIR / "Player.log"
KSP_PLAYER_PREV_LOG = KSP_USER_DIR / "Player-prev.log"
KSP_SAVE_UID_FILE = ".terranova_save_uid"
SATELLITES_PAGE_SIZE = 20
SATELLITE_STATUS_ACTIVE = "Activo"
SATELLITE_STATUS_MAINTENANCE = "Mantenimiento"
SATELLITE_STATUS_OFFLINE = "Fuera de servicio"
DEFAULT_SATELLITE_GROUPS = {
    "LEO": {
        "name": "LEO",
        "full_name": "Low Earth Orbit",
        "description": "0 km - 900 km",
        "min_alt_km": 0,
        "max_alt_km": 900,
        "system": True,
    },
    "MEO": {
        "name": "MEO",
        "full_name": "Medium Earth Orbit",
        "description": "900 km - 2800 km",
        "min_alt_km": 900,
        "max_alt_km": 2800,
        "system": True,
    },
    "GEO": {
        "name": "GEO",
        "full_name": "Geostationary Earth Orbit",
        "description": "2800 km - 2900 km",
        "min_alt_km": 2800,
        "max_alt_km": 2900,
        "system": True,
    },
    "EEO": {
        "name": "EEO",
        "full_name": "External Earth Orbit",
        "description": "más de 2900 km",
        "min_alt_km": 2900,
        "max_alt_km": None,
        "system": True,
    },
    "ESTACIONES ESPACIALES": {
        "name": "ESTACIONES ESPACIALES",
        "full_name": "Estaciones Espaciales",
        "description": "Objetos con icono de estación espacial",
        "min_alt_km": None,
        "max_alt_km": None,
        "system": True,
    },
    "BASURA ESPACIAL": {
        "name": "BASURA ESPACIAL",
        "full_name": "Basura Espacial",
        "description": "Objetos con icono de basura espacial",
        "min_alt_km": None,
        "max_alt_km": None,
        "system": True,
    },
}


def apply_shadow(widget: QWidget, blur: int = 28, alpha: int = 90) -> None:
    # Se elimina el efecto de sombreado (remarcado oscuro) para dejar la interfaz plana
    pass


def fade_in(widget: QWidget, duration: int = 700) -> None:
    # Los widgets embebidos en la pila principal suelen contener pintura activa
    # o timers; en ellos la opacidad por efecto de Qt puede generar conflictos
    # de QPainter. Limitamos la animación de opacidad a ventanas reales.
    if not widget.isWindow():
        widget._fade_animation = None
        return
    current_effect = widget.graphicsEffect()
    if isinstance(current_effect, QGraphicsOpacityEffect):
        effect = current_effect
    else:
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    previous = getattr(widget, "_fade_animation", None)
    if previous is not None:
        try:
            previous.stop()
        except Exception:
            pass
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    widget._fade_animation = animation
    animation.start()


def fade_out(widget: QWidget, finished, duration: int = 420) -> None:
    if not widget.isWindow():
        QTimer.singleShot(duration, finished)
        return
    current_effect = widget.graphicsEffect()
    if isinstance(current_effect, QGraphicsOpacityEffect):
        effect = current_effect
    else:
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    effect.setOpacity(1.0)
    previous = getattr(widget, "_fade_animation", None)
    if previous is not None:
        try:
            previous.stop()
        except Exception:
            pass
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


class _LegacyModuleCard(QPushButton):
    def __init__(self, title: str, available: bool, parent: QWidget | None = None):
        super().__init__(title, parent)
        self.available = available
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(118)
        self.setObjectName("moduleCard" if available else "moduleCardDisabled")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._animate_hover(True)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._animate_hover(False)

    def _animate_hover(self, active: bool) -> None:
        # Evitar cambios de geometría: en un grid puede hacer que las cards
        # salten o desaparezcan al recalcular el layout.
        if not self.isEnabled():
            return
        self.setProperty("hovered", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class ModuleCardImagePanel(QWidget):
    zoomChanged = pyqtSignal()

    def __init__(self, pixmap: QPixmap, parent: QWidget | None = None):
        super().__init__(parent)
        self._source_pixmap = pixmap
        self._zoom = 1.0
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._zoom_anim = QPropertyAnimation(self, b"zoom", self)
        self._zoom_anim.setDuration(180)
        self._zoom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def sizeHint(self) -> QSize:
        return QSize(320, 186)

    def minimumSizeHint(self) -> QSize:
        return QSize(240, 160)

    def getZoom(self) -> float:
        return self._zoom

    def setZoom(self, value: float) -> None:
        value = max(1.0, min(1.08, float(value)))
        if abs(self._zoom - value) < 0.0001:
            return
        self._zoom = value
        self.zoomChanged.emit()
        self.update()

    zoom = pyqtProperty(float, fget=getZoom, fset=setZoom, notify=zoomChanged)

    def set_hover(self, active: bool) -> None:
        self._zoom_anim.stop()
        self._zoom_anim.setStartValue(self._zoom)
        self._zoom_anim.setEndValue(1.06 if active else 1.0)
        self._zoom_anim.start()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipRect(self.rect())

        rect = self.rect()
        if self._source_pixmap.isNull():
            painter.fillRect(rect, QColor(8, 15, 24))
            painter.fillRect(rect, QColor(18, 33, 48, 110))
            return

        target_size = QSize(
            max(1, int(rect.width() * self._zoom)),
            max(1, int(rect.height() * self._zoom)),
        )
        scaled = self._source_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (rect.width() - scaled.width()) // 2
        y = (rect.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.fillRect(rect, QColor(6, 13, 20, 40))
        painter.fillRect(rect.adjusted(0, rect.height() - 52, 0, 0), QColor(8, 12, 18, 70))


class ModuleCard(QWidget):
    clicked = pyqtSignal()

    def __init__(self, title: str, available: bool, image_name: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.title = title
        self.available = available
        self.image_name = image_name
        self.setObjectName("moduleCard" if available else "moduleCardDisabled")
        self.setCursor(Qt.CursorShape.PointingHandCursor if available else Qt.CursorShape.ArrowCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(250)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.image_panel = ModuleCardImagePanel(self._load_pixmap())
        self.image_panel.setObjectName("moduleCardImagePanel")
        self.image_panel.setMinimumHeight(164)
        self.image_panel.setMaximumHeight(164)
        root.addWidget(self.image_panel, 1)

        self.text_panel = QFrame()
        self.text_panel.setObjectName("moduleCardTextPanel")
        self.text_panel.setFixedHeight(86)
        self.text_panel.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        text_layout = QVBoxLayout(self.text_panel)
        text_layout.setContentsMargins(18, 12, 18, 12)
        text_layout.setSpacing(2)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("moduleCardTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.subtitle_label = QLabel(self._subtitle_text())
        self.subtitle_label.setObjectName("moduleCardSubtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.subtitle_label)
        text_layout.addStretch()
        root.addWidget(self.text_panel)

    def _subtitle_text(self) -> str:
        if self.available:
            return " "
        return "Módulo no disponible actualmente."

    def _load_pixmap(self) -> QPixmap:
        candidates: list[Path] = []
        if self.image_name:
            candidates.append(PANEL_IMAGE_DIR / self.image_name)
        candidates.extend([LOGO_PATH_CORT, LOGO_PATH])
        for path in candidates:
            if path.exists():
                pixmap = QPixmap(str(path))
                if not pixmap.isNull():
                    return pixmap
        return QPixmap()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        if self.available:
            self.image_panel.set_hover(True)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.image_panel.set_hover(False)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.available and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class CommandCenter(QWidget):
    def __init__(self, on_module_selected, parent: QWidget | None = None):
        super().__init__(parent)
        self.on_module_selected = on_module_selected
        self._active_save_context: dict | None = None
        self._build_ui()
        self._save_context_timer = QTimer(self)
        self._save_context_timer.timeout.connect(self._refresh_active_save_context)
        self._save_context_timer.start(2500)
        self._refresh_active_save_context()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 16, 24, 24)
        content_layout.setSpacing(24)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        logo = LogoLabel(QSize(460, 170))
        header_layout.addWidget(logo, 1, alignment=Qt.AlignmentFlag.AlignCenter)
        self.save_context_card = QFrame()
        self.save_context_card.setObjectName("saveContextCard")
        self.save_context_card.setFixedWidth(300)
        save_layout = QVBoxLayout(self.save_context_card)
        save_layout.setContentsMargins(14, 12, 14, 12)
        save_layout.setSpacing(4)
        self.save_context_title = QLabel("Partida activa")
        self.save_context_title.setObjectName("status")
        self.save_context_title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.save_context_value = QLabel("Detectando save...")
        self.save_context_value.setWordWrap(True)
        self.save_context_value.setStyleSheet("color: #dce9f6; font-size: 13px; font-weight: 700;")
        self.save_context_meta = QLabel("")
        self.save_context_meta.setWordWrap(True)
        self.save_context_meta.setObjectName("muted")
        save_layout.addWidget(self.save_context_title)
        save_layout.addWidget(self.save_context_value)
        save_layout.addWidget(self.save_context_meta)
        header_layout.addWidget(self.save_context_card, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        content_layout.addWidget(header)

        grid_container = QWidget()
        self.grid = QGridLayout(grid_container)
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(18)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.module_cards: list[ModuleCard] = []
        for index, (name, target) in enumerate(MODULES.items()):
            card = ModuleCard(name, bool(target), MODULE_PANEL_IMAGES.get(name))
            card.clicked.connect(lambda module=name: self.on_module_selected(module))
            self.module_cards.append(card)
            row, col = divmod(index, 3)
            self.grid.addWidget(card, row, col)

        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnStretch(2, 1)
        content_layout.addWidget(grid_container)
        content_layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll)
        self.scroll_area = scroll
        self.grid_container = grid_container
        self._relayout_cards()

    def _refresh_active_save_context(self) -> None:
        context = _active_ksp_save_context()
        if context is None:
            self._active_save_context = None
            self.save_context_value.setText("Sin partida detectada")
            self.save_context_meta.setText("Abre un save en KSP para mostrarlo aquí.")
            self.save_context_card.setProperty("state", "empty")
            self.save_context_card.style().unpolish(self.save_context_card)
            self.save_context_card.style().polish(self.save_context_card)
            return

        if self._active_save_context == context:
            return

        self._active_save_context = context
        save_name = context.get("save_name", "Desconocido")
        save_path = context.get("save_path", "")
        short_uid = str(context.get("save_uid", ""))[:8].upper()
        self.save_context_value.setText(save_name)
        self.save_context_meta.setText(f"ID {short_uid} · {save_path}")
        self.save_context_card.setProperty("state", "active")
        self.save_context_card.style().unpolish(self.save_context_card)
        self.save_context_card.style().polish(self.save_context_card)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout_cards()

    def _relayout_cards(self) -> None:
        if not hasattr(self, "grid") or not hasattr(self, "module_cards"):
            return
        width = max(1, self.width())
        columns = 1 if width < 760 else 2 if width < 1080 else 3
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item and item.widget():
                item.widget().setParent(None)
        for index, card in enumerate(self.module_cards):
            row, col = divmod(index, columns)
            self.grid.addWidget(card, row, col)
        for col in range(columns):
            self.grid.setColumnStretch(col, 1)


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


def _press_date_sort_key(value: str) -> tuple[int, int, int, int]:
    date_obj = QDate.fromString(value, "yyyy-MM-dd")
    if not date_obj.isValid():
        date_obj = QDate.fromString(value, "dd/MM/yyyy")
    if not date_obj.isValid():
        return (0, 0, 0, 0)
    return (date_obj.year(), date_obj.month(), date_obj.day(), 1)


def _press_plain_text_from_html(html: str) -> str:
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<head\b[^>]*>.*?</head>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _press_summary_from_blocks(blocks: list[dict], limit: int = 140) -> str:
    for block in blocks:
        if str(block.get("type", "")).strip() != "text":
            continue
        plain = str(block.get("plain") or _press_plain_text_from_html(str(block.get("html") or ""))).strip()
        if plain:
            return _shorten_text(plain.replace("\n", " "), limit)
    return "Sin resumen disponible."


def _press_summary_from_text(body_html: str, limit: int = 140) -> str:
    plain = _press_plain_text_from_html(body_html)
    if not plain:
        return "Sin resumen disponible."
    return _shorten_text(plain.replace("\n", " "), limit)


def _press_legacy_body_and_attachments(blocks: list[dict]) -> tuple[str, list[dict]]:
    text_parts: list[str] = []
    attachments: list[dict] = []
    for block in blocks:
        block_type = str(block.get("type", "")).strip().lower()
        if block_type == "text":
            html = str(block.get("html") or "")
            plain = str(block.get("plain") or _press_plain_text_from_html(html)).strip()
            text_parts.append(html.strip() or plain)
            continue
        if block_type == "carousel":
            for item in list(block.get("items", []) or []):
                path = str(item.get("path", "")).strip()
                if path:
                    attachments.append({
                        "path": path,
                        "label": str(item.get("label") or Path(path).stem or "Imagen").strip(),
                        "type": "image",
                    })
            continue
        path = str(block.get("path", "")).strip()
        if path:
            media_type = block_type if block_type in {"image", "video", "document"} else _press_media_kind_for_path(Path(path))
            attachments.append({
                "path": path,
                "label": str(block.get("label") or Path(path).stem or "Archivo").strip(),
                "type": media_type,
            })
    body_html = "\n".join(part for part in text_parts if part).strip()
    return body_html, attachments


def _press_media_kind_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}:
        return "image"
    if suffix in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
        return "video"
    return "document"


def _press_encode_attachment_ref(path: str) -> str:
    token = base64.urlsafe_b64encode(str(path).encode("utf-8")).decode("ascii").rstrip("=")
    return f"attachment:{token}"


def _press_decode_attachment_ref(href: str) -> str | None:
    if not href.startswith("attachment:"):
        return None
    token = href.split(":", 1)[1].strip()
    if not token:
        return None
    padding = "=" * (-len(token) % 4)
    try:
        return base64.urlsafe_b64decode(token + padding).decode("utf-8")
    except Exception:
        return None


def _press_rewrite_attachment_refs(body_html: str, path_map: dict[str, str]) -> str:
    if not body_html or not path_map:
        return body_html
    rewritten = body_html
    for old_path, new_path in path_map.items():
        old_href = _press_encode_attachment_ref(old_path)
        new_href = _press_encode_attachment_ref(new_path)
        rewritten = rewritten.replace(f'href="{old_href}"', f'href="{new_href}"')
        rewritten = rewritten.replace(f"href='{old_href}'", f"href='{new_href}'")
    return rewritten


def _press_crop_rect_from_payload(payload: dict | None) -> QRectF | None:
    if not isinstance(payload, dict):
        return None
    try:
        x = float(payload.get("x", 0.0))
        y = float(payload.get("y", 0.0))
        w = float(payload.get("w", 0.0))
        h = float(payload.get("h", 0.0))
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return QRectF(x, y, w, h)


def _press_crop_payload_from_rect(rect: QRectF | None) -> dict[str, float]:
    if rect is None or rect.width() <= 0 or rect.height() <= 0:
        return {}
    return {
        "x": max(0.0, min(1.0, float(rect.x()))),
        "y": max(0.0, min(1.0, float(rect.y()))),
        "w": max(0.0, min(1.0, float(rect.width()))),
        "h": max(0.0, min(1.0, float(rect.height()))),
    }


def _press_center_horizontal_crop(pixmap: QPixmap) -> QRectF | None:
    if pixmap.isNull():
        return None
    source_w = float(max(1, pixmap.width()))
    source_h = float(max(1, pixmap.height()))
    target_aspect = 16.0 / 9.0
    source_aspect = source_w / source_h
    if source_aspect > target_aspect:
        crop_h = 1.0
        crop_w = target_aspect / source_aspect
    else:
        crop_w = 1.0
        crop_h = source_aspect / target_aspect
    crop_x = (1.0 - crop_w) / 2.0
    crop_y = (1.0 - crop_h) / 2.0
    return QRectF(crop_x, crop_y, crop_w, crop_h)


def _press_crop_image(pixmap: QPixmap, crop: QRectF | None) -> QPixmap:
    crop_rect = crop or _press_center_horizontal_crop(pixmap)
    if pixmap.isNull() or crop_rect is None or crop_rect.isNull():
        return pixmap
    crop_rect = QRectF(
        max(0.0, min(1.0, crop_rect.x())),
        max(0.0, min(1.0, crop_rect.y())),
        max(0.05, min(1.0, crop_rect.width())),
        max(0.05, min(1.0, crop_rect.height())),
    )
    if crop_rect.x() + crop_rect.width() > 1.0:
        crop_rect.setWidth(1.0 - crop_rect.x())
    if crop_rect.y() + crop_rect.height() > 1.0:
        crop_rect.setHeight(1.0 - crop_rect.y())
    x = int(crop_rect.x() * pixmap.width())
    y = int(crop_rect.y() * pixmap.height())
    w = max(1, int(crop_rect.width() * pixmap.width()))
    h = max(1, int(crop_rect.height() * pixmap.height()))
    return pixmap.copy(x, y, w, h)


def _press_pixmap_to_data_uri(pixmap: QPixmap) -> str:
    if pixmap.isNull():
        return ""
    buffer = QByteArray()
    byte_buffer = QBuffer(buffer)
    byte_buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    pixmap.save(byte_buffer, "PNG")
    byte_buffer.close()
    encoded = base64.b64encode(bytes(buffer)).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _press_relativize_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(BASE_DIR))
    except Exception:
        return str(path.resolve())


class PressStore:
    def __init__(self, notes_file: Path = PRESS_FILE):
        self.notes_file = notes_file
        self.notes: list[dict] = []
        self.next_id = 1
        self.load()

    def _ensure_structure(self) -> None:
        for folder in (PRESS_DIR, PRESS_MEDIA_DIR, PRESS_MEDIA_IMAGES_DIR, PRESS_MEDIA_VIDEOS_DIR, PRESS_MEDIA_DOCUMENTS_DIR):
            folder.mkdir(parents=True, exist_ok=True)

    def load(self) -> None:
        self._ensure_structure()
        payload = _load_json_file(self.notes_file, {})
        self.next_id = int(payload.get("next_id", 1)) if isinstance(payload, dict) else 1
        raw_notes = payload.get("notes", []) if isinstance(payload, dict) else []
        self.notes = []
        if isinstance(raw_notes, list):
            for entry in raw_notes:
                if isinstance(entry, dict):
                    self.notes.append(entry)
        self._normalize_notes(import_media=False)

    def save(self) -> None:
        self._ensure_structure()
        self._normalize_notes(import_media=True)
        _save_json_file(self.notes_file, {
            "next_id": self.next_id,
            "notes": self.notes,
        })
        self._prune_unused_media()

    def _allocate_id(self) -> int:
        note_id = int(self.next_id)
        self.next_id += 1
        return note_id

    def get_note(self, note_id: int) -> dict | None:
        for note in self.notes:
            if int(note.get("id", 0)) == int(note_id):
                return note
        return None

    def upsert_note(self, payload: dict) -> dict:
        note_id = int(payload.get("id") or 0)
        if note_id <= 0:
            note_id = self._allocate_id()
        existing = self.get_note(note_id)
        if existing is None:
            existing = {"id": note_id, "created_at": time.time()}
            self.notes.append(existing)
        existing.update(payload)
        existing["id"] = note_id
        existing.setdefault("created_at", time.time())
        existing["updated_at"] = time.time()
        self.save()
        return existing

    def delete_note(self, note_id: int) -> bool:
        before = len(self.notes)
        self.notes = [note for note in self.notes if int(note.get("id", 0)) != int(note_id)]
        if len(self.notes) == before:
            return False
        self.save()
        return True

    def query_notes(self, text: str = "") -> list[dict]:
        term = _normalize_key(text)
        notes = [dict(note) for note in self.notes]
        if term:
            notes = [note for note in notes if self._matches_query(note, term)]
        notes.sort(key=self._sort_key, reverse=True)
        return notes

    def _matches_query(self, note: dict, term: str) -> bool:
        haystack = str(note.get("title", ""))
        return term in _normalize_key(haystack)

    def _sort_key(self, note: dict) -> tuple:
        date_key = _press_date_sort_key(str(note.get("date", "")))
        updated = float(note.get("updated_at") or note.get("created_at") or 0.0)
        return (*date_key, updated, int(note.get("id", 0)))

    def _normalize_notes(self, import_media: bool) -> None:
        normalized: list[dict] = []
        max_id = 0
        for note in self.notes:
            note_id = int(note.get("id") or 0)
            if note_id <= 0:
                note_id = self._allocate_id()
            max_id = max(max_id, note_id)
            legacy_blocks = list(note.get("blocks", []) or [])
            body_html = str(note.get("body_html", "")).strip()
            main_image = str(note.get("main_image", "")).strip()
            main_image_crop = _press_crop_rect_from_payload(note.get("main_image_crop"))
            attachments = list(note.get("attachments", []) or [])
            if legacy_blocks and not body_html and not attachments:
                body_html, attachments = _press_legacy_body_and_attachments(legacy_blocks)
            body_html = self._normalize_body_html(body_html)
            attachments, path_map = self._normalize_attachments(note_id, attachments, import_media=import_media)
            main_image = self._normalize_media_path(note_id, main_image, "image", import_media=import_media)
            body_html = _press_rewrite_attachment_refs(body_html, path_map)
            # El resumen se recalcula siempre a partir del contenido actual de la nota
            # para evitar que quede un resumen obsoleto o con restos de marcado/CSS
            # si la nota se editó después de haberse guardado por primera vez.
            summary = _press_summary_from_text(body_html)
            if not summary:
                summary = _press_plain_text_from_html(str(note.get("summary") or "").strip())
            summary = _shorten_text(summary.replace("\n", " "), 140) if summary else "Sin resumen disponible."
            normalized.append({
                "id": note_id,
                "title": str(note.get("title", "")).strip(),
                "author": str(note.get("author", "")).strip(),
                "date": self._normalize_date(str(note.get("date", "")).strip()),
                "importance": str(note.get("importance", "")).strip(),
                "body_html": body_html,
                "main_image": main_image,
                "main_image_crop": _press_crop_payload_from_rect(main_image_crop),
                "attachments": attachments,
                "summary": summary,
                "created_at": float(note.get("created_at") or time.time()),
                "updated_at": float(note.get("updated_at") or note.get("created_at") or time.time()),
            })
        self.notes = sorted(normalized, key=self._sort_key, reverse=True)
        if self.next_id <= max_id:
            self.next_id = max_id + 1

    def _normalize_body_html(self, body_html: str) -> str:
        body_html = str(body_html or "").strip()
        if not body_html:
            return ""
        return body_html

    def _normalize_date(self, value: str) -> str:
        if not value:
            return QDate.currentDate().toString("yyyy-MM-dd")
        for fmt in ("yyyy-MM-dd", "dd/MM/yyyy", "d/M/yyyy", "dd-MM-yyyy"):
            date_obj = QDate.fromString(value, fmt)
            if date_obj.isValid():
                return date_obj.toString("yyyy-MM-dd")
        date_obj = QDate.currentDate()
        return date_obj.toString("yyyy-MM-dd")

    def _media_target_dir(self, media_type: str) -> Path:
        if media_type == "image":
            return PRESS_MEDIA_IMAGES_DIR
        if media_type == "video":
            return PRESS_MEDIA_VIDEOS_DIR
        return PRESS_MEDIA_DOCUMENTS_DIR

    def _import_media_file(self, note_id: int, source_path: str, media_type: str) -> str:
        source = Path(source_path)
        if not source.exists():
            return source_path
        source = source.resolve()
        try:
            if source.is_relative_to(PRESS_DIR):
                return _press_relativize_path(source)
        except Exception:
            pass
        target_dir = self._media_target_dir(media_type)
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower()
        stem = _normalize_key(source.stem) or f"note_{note_id}"
        destination = target_dir / f"{stem}_{note_id}_{uuid.uuid4().hex[:10]}{suffix}"
        shutil.copy2(source, destination)
        return _press_relativize_path(destination)

    def _normalize_attachments(self, note_id: int, attachments: list[dict], import_media: bool) -> tuple[list[dict], dict[str, str]]:
        normalized: list[dict] = []
        path_map: dict[str, str] = {}
        for entry in attachments:
            raw_path = str(entry.get("path", "")).strip()
            if not raw_path:
                continue
            resolved = _resolve_press_path(raw_path)
            attachment_type = str(entry.get("type") or _press_media_kind_for_path(resolved)).strip().lower()
            if attachment_type not in {"image", "video", "document"}:
                attachment_type = _press_media_kind_for_path(resolved)
            normalized_path = raw_path
            if resolved.exists() and import_media:
                normalized_path = self._import_media_file(note_id, str(resolved), attachment_type)
            elif resolved.is_absolute():
                normalized_path = _press_relativize_path(resolved)
            normalized.append({
                "path": normalized_path,
                "label": str(entry.get("label") or resolved.stem or "Archivo").strip(),
                "type": attachment_type,
            })
            path_map[raw_path] = normalized_path
        return normalized, path_map

    def _normalize_media_path(self, note_id: int, raw_path: str, media_type: str, import_media: bool) -> str:
        raw_path = str(raw_path or "").strip()
        if not raw_path:
            return ""
        resolved = _resolve_press_path(raw_path)
        if resolved.exists() and import_media:
            return self._import_media_file(note_id, str(resolved), media_type)
        if resolved.is_absolute():
            return _press_relativize_path(resolved)
        return raw_path

    def _iter_media_paths(self) -> set[Path]:
        paths: set[Path] = set()
        for note in self.notes:
            self._collect_media_path(paths, str(note.get("main_image", "")))
            for attachment in list(note.get("attachments", []) or []):
                self._collect_media_path(paths, str(attachment.get("path", "")))
            for block in list(note.get("blocks", []) or []):
                if block.get("type") == "carousel":
                    for item in list(block.get("items", []) or []):
                        self._collect_media_path(paths, str(item.get("path", "")))
                else:
                    self._collect_media_path(paths, str(block.get("path", "")))
        return paths

    def _collect_media_path(self, paths: set[Path], value: str) -> None:
        if not value:
            return
        path = Path(value)
        if not path.is_absolute():
            path = (BASE_DIR / path).resolve()
        if PRESS_DIR in path.parents or path.parent == PRESS_DIR:
            paths.add(path)

    def _prune_unused_media(self) -> None:
        referenced = self._iter_media_paths()
        for directory in (PRESS_MEDIA_IMAGES_DIR, PRESS_MEDIA_VIDEOS_DIR, PRESS_MEDIA_DOCUMENTS_DIR):
            if not directory.exists():
                continue
            for file_path in directory.rglob("*"):
                if file_path.is_file() and file_path.resolve() not in referenced:
                    try:
                        file_path.unlink()
                    except Exception:
                        pass


def _resolve_press_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (BASE_DIR / path).resolve()


class PressTextEdit(QTextEdit):
    activated = pyqtSignal(object)
    reference_requested = pyqtSignal()

    def focusInEvent(self, event) -> None:
        self.activated.emit(self)
        super().focusInEvent(event)

    def keyPressEvent(self, event) -> None:
        super().keyPressEvent(event)
        try:
            if event.text() == "@":
                self.reference_requested.emit()
        except Exception:
            pass


class PressImageCropWidget(QWidget):
    cropChanged = pyqtSignal()
    HANDLE_SIZE = 12

    def __init__(self, pixmap: QPixmap, parent: QWidget | None = None):
        super().__init__(parent)
        self._source = pixmap
        self._selection = QRectF()
        self._zoom = 1.0
        self._dragging = False
        self._drag_mode = "move"
        self._active_handle = ""
        self._drag_offset = QPointF()
        self._display_rect = QRectF()
        self.setMouseTracking(True)
        self.setMinimumSize(640, 360)

    def sizeHint(self) -> QSize:
        return QSize(760, 428)

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._source = pixmap
        self._selection = QRectF()
        self._zoom = 1.0
        self.update()

    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, value: float) -> None:
        value = max(0.5, min(2.5, float(value)))
        if abs(self._zoom - value) < 0.0001:
            return
        self._zoom = value
        if self._selection.isNull():
            self._selection = self._default_selection()
        self.cropChanged.emit()
        self.update()

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * 1.15)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / 1.15)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoom_in()
        elif delta < 0:
            self.zoom_out()
        event.accept()

    def selection(self) -> QRectF | None:
        return self._normalized_selection() if not self._selection.isNull() else None

    def _image_rect(self) -> QRectF:
        if self._source.isNull():
            return QRectF()
        scaled = self._source.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        scaled = QSize(max(1, int(scaled.width() * self._zoom)), max(1, int(scaled.height() * self._zoom)))
        x = (self.width() - scaled.width()) / 2.0
        y = (self.height() - scaled.height()) / 2.0
        return QRectF(x, y, scaled.width(), scaled.height())

    def _selection_aspect(self) -> float:
        return 16.0 / 9.0

    def _default_selection(self) -> QRectF:
        image_rect = self._image_rect()
        if image_rect.isNull():
            return QRectF()
        width = image_rect.width() * 0.62
        height = width / self._selection_aspect()
        if height > image_rect.height():
            height = image_rect.height() * 0.62
            width = height * self._selection_aspect()
        x = image_rect.center().x() - width / 2.0
        y = image_rect.center().y() - height / 2.0
        return self._clamp_selection(QRectF(x, y, width, height))

    def _clamp_selection(self, rect: QRectF) -> QRectF:
        image_rect = self._image_rect()
        if image_rect.isNull():
            return QRectF()
        width = min(rect.width(), image_rect.width())
        height = width / self._selection_aspect()
        if height > image_rect.height():
            height = image_rect.height()
            width = height * self._selection_aspect()
        x = max(image_rect.left(), min(rect.left(), image_rect.right() - width))
        y = max(image_rect.top(), min(rect.top(), image_rect.bottom() - height))
        return QRectF(x, y, width, height)

    def _handle_rects(self) -> dict[str, QRectF]:
        if self._selection.isNull():
            return {}
        size = float(self.HANDLE_SIZE)
        half = size / 2.0
        return {
            "tl": QRectF(self._selection.left() - half, self._selection.top() - half, size, size),
            "tr": QRectF(self._selection.right() - half, self._selection.top() - half, size, size),
            "bl": QRectF(self._selection.left() - half, self._selection.bottom() - half, size, size),
            "br": QRectF(self._selection.right() - half, self._selection.bottom() - half, size, size),
        }

    def _handle_at_point(self, pos: QPointF) -> str:
        for name, rect in self._handle_rects().items():
            if rect.contains(pos):
                return name
        return ""

    def _selection_from_corner(self, handle: str, pos: QPointF) -> QRectF:
        image_rect = self._image_rect()
        if image_rect.isNull():
            return QRectF()
        pos = QPointF(
            max(image_rect.left(), min(pos.x(), image_rect.right())),
            max(image_rect.top(), min(pos.y(), image_rect.bottom())),
        )
        if handle == "tl":
            anchor = self._selection.bottomRight()
            width = max(20.0, anchor.x() - pos.x())
            height = width / self._selection_aspect()
            if anchor.y() - height < image_rect.top():
                height = max(20.0, anchor.y() - image_rect.top())
                width = height * self._selection_aspect()
            x = anchor.x() - width
            y = anchor.y() - height
        elif handle == "tr":
            anchor = self._selection.bottomLeft()
            width = max(20.0, pos.x() - anchor.x())
            height = width / self._selection_aspect()
            if anchor.y() - height < image_rect.top():
                height = max(20.0, anchor.y() - image_rect.top())
                width = height * self._selection_aspect()
            x = anchor.x()
            y = anchor.y() - height
        elif handle == "bl":
            anchor = self._selection.topRight()
            width = max(20.0, anchor.x() - pos.x())
            height = width / self._selection_aspect()
            if anchor.y() + height > image_rect.bottom():
                height = max(20.0, image_rect.bottom() - anchor.y())
                width = height * self._selection_aspect()
            x = anchor.x() - width
            y = anchor.y()
        else:  # br
            anchor = self._selection.topLeft()
            width = max(20.0, pos.x() - anchor.x())
            height = width / self._selection_aspect()
            if anchor.y() + height > image_rect.bottom():
                height = max(20.0, image_rect.bottom() - anchor.y())
                width = height * self._selection_aspect()
            x = anchor.x()
            y = anchor.y()
        return self._clamp_selection(QRectF(x, y, width, height))

    def _normalized_selection(self) -> QRectF:
        if self._selection.isNull():
            return QRectF()
        image_rect = self._image_rect()
        if image_rect.isNull():
            return QRectF()
        left = (self._selection.left() - image_rect.left()) / image_rect.width()
        top = (self._selection.top() - image_rect.top()) / image_rect.height()
        width = self._selection.width() / image_rect.width()
        height = self._selection.height() / image_rect.height()
        return QRectF(left, top, width, height)

    def set_normalized_selection(self, rect: QRectF | None) -> None:
        image_rect = self._image_rect()
        if image_rect.isNull() or rect is None or rect.isNull():
            self._selection = self._default_selection()
        else:
            self._selection = self._clamp_selection(
                QRectF(
                    image_rect.left() + rect.x() * image_rect.width(),
                    image_rect.top() + rect.y() * image_rect.height(),
                    rect.width() * image_rect.width(),
                    rect.height() * image_rect.height(),
                )
            )
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._selection.isNull():
            self._selection = self._default_selection()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), QColor(7, 16, 25))

        image_rect = self._image_rect()
        self._display_rect = image_rect
        if self._source.isNull() or image_rect.isNull():
            painter.setPen(QColor("#8fa4b8"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Selecciona una imagen para recortarla")
            return

        scaled = self._source.scaled(
            image_rect.size().toSize(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(int(image_rect.x()), int(image_rect.y()), scaled)

        if self._selection.isNull():
            self._selection = self._default_selection()
        sel = self._selection
        painter.fillRect(image_rect, QColor(0, 0, 0, 80))
        painter.fillRect(sel, QColor(0, 0, 0, 0))
        painter.setPen(QPen(QColor("#4da3ff"), 2))
        painter.drawRect(sel)
        painter.setBrush(QColor("#4da3ff"))
        painter.setPen(Qt.PenStyle.NoPen)
        for rect in self._handle_rects().values():
            painter.drawRoundedRect(rect, 2, 2)

    def mousePressEvent(self, event) -> None:
        if self._source.isNull() or not self._display_rect.contains(event.position()):
            return
        handle = self._handle_at_point(event.position())
        if handle:
            self._dragging = True
            self._drag_mode = "corner"
            self._active_handle = handle
        elif self._selection.contains(event.position()):
            self._dragging = True
            self._drag_mode = "move"
            self._drag_offset = event.position() - self._selection.topLeft()
        else:
            width = self._display_rect.width() * 0.62
            height = width / self._selection_aspect()
            self._selection = self._clamp_selection(QRectF(event.position().x() - width / 2, event.position().y() - height / 2, width, height))
            self._dragging = True
            self._drag_mode = "move"
            self._active_handle = ""
            self._drag_offset = event.position() - self._selection.topLeft()
            self.cropChanged.emit()
            self.update()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            return
        if self._drag_mode == "corner" and self._active_handle:
            self._selection = self._selection_from_corner(self._active_handle, event.position())
        else:
            new_top_left = event.position() - self._drag_offset
            self._selection = self._clamp_selection(QRectF(new_top_left, self._selection.size()))
        self.cropChanged.emit()
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False
        self._drag_mode = "move"
        self._active_handle = ""
        super().mouseReleaseEvent(event)


class PressImageCropDialog(QDialog):
    def __init__(self, image_path: str, crop: QRectF | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar imagen principal")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setStyleSheet("QDialog { background: #07111d; }")
        self.resize(920, 620)
        self._source_path = str(image_path)
        self._result_crop: QRectF | None = crop

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        panel = GlassPanel()
        panel.setObjectName("modalPanel")
        panel.setStyleSheet("""
            QFrame#modalPanel {
                background: #101d2c;
                border: 1px solid rgba(126, 164, 196, 90);
                border-radius: 14px;
            }
        """)
        outer.addWidget(panel)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 18)
        panel_layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Imagen principal")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.reject)
        header.addWidget(close_btn)
        panel_layout.addLayout(header)

        info = QLabel("Arrastra el rectángulo para elegir el área visible. La imagen se mostrará siempre en horizontal.")
        info.setObjectName("muted")
        info.setWordWrap(True)
        panel_layout.addWidget(info)

        self.crop_widget = PressImageCropWidget(QPixmap(str(_resolve_press_path(self._source_path))))
        panel_layout.addWidget(self.crop_widget, 1)
        if crop is not None:
            self.crop_widget.set_normalized_selection(crop)

        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Zoom"))
        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setFixedWidth(40)
        zoom_out_btn.clicked.connect(self.crop_widget.zoom_out)
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedWidth(40)
        zoom_in_btn.clicked.connect(self.crop_widget.zoom_in)
        reset_zoom_btn = QPushButton("Restablecer")
        reset_zoom_btn.clicked.connect(lambda: self.crop_widget.set_zoom(1.0))
        zoom_row.addWidget(zoom_out_btn)
        zoom_row.addWidget(zoom_in_btn)
        zoom_row.addWidget(reset_zoom_btn)
        zoom_row.addStretch()
        panel_layout.addLayout(zoom_row)

        footer = QHBoxLayout()
        footer.addStretch()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("Usar recorte")
        ok_btn.setObjectName("primaryButton")
        ok_btn.clicked.connect(self.accept)
        footer.addWidget(cancel_btn)
        footer.addWidget(ok_btn)
        panel_layout.addLayout(footer)

    def result_crop(self) -> QRectF | None:
        return self.crop_widget.selection()


class PressTextBlockWidget(QFrame):
    activated = pyqtSignal(object)
    remove_requested = pyqtSignal(object)
    insert_requested = pyqtSignal(str)

    def __init__(self, html: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("pressBlock")
        self.setProperty("kind", "text")
        self._build_ui(html)

    def _build_ui(self, html: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        title = QLabel("Bloque de texto")
        title.setObjectName("status")
        header.addWidget(title)
        header.addStretch()
        insert_btn = QPushButton("Insertar")
        insert_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        insert_btn.clicked.connect(lambda: self.insert_requested.emit("text"))
        remove_btn = QPushButton("Eliminar")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        header.addWidget(insert_btn)
        header.addWidget(remove_btn)
        layout.addLayout(header)

        self.editor = PressTextEdit()
        self.editor.setAcceptRichText(True)
        self.editor.setPlaceholderText("Escribe el contenido de la nota...")
        self.editor.setMinimumHeight(160)
        self.editor.activated.connect(lambda _: self.activated.emit(self))
        if html:
            self.editor.setHtml(html)
        layout.addWidget(self.editor)

    def set_html(self, html: str) -> None:
        if html:
            self.editor.setHtml(html)
        else:
            self.editor.setPlainText("")

    def html(self) -> str:
        return self.editor.toHtml()

    def plain_text(self) -> str:
        return self.editor.toPlainText()

    def split_at_cursor(self) -> tuple[str, str]:
        text = self.editor.toPlainText()
        cursor = self.editor.textCursor()
        position = max(0, min(cursor.position(), len(text)))
        return text[:position], text[position:]


class PressMediaBlockWidget(QFrame):
    activated = pyqtSignal(object)
    remove_requested = pyqtSignal(object)
    replace_requested = pyqtSignal(object)

    def __init__(self, block_type: str, data: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.block_type = block_type
        self.setObjectName("pressBlock")
        self.setProperty("kind", block_type)
        self._build_ui()
        if data:
            self.set_data(data)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self)
        super().mousePressEvent(event)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self.kind_label = QLabel(self._kind_title())
        self.kind_label.setObjectName("status")
        header.addWidget(self.kind_label)
        header.addStretch()
        replace_btn = QPushButton("Cambiar")
        replace_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        replace_btn.clicked.connect(lambda: self.replace_requested.emit(self))
        remove_btn = QPushButton("Eliminar")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        header.addWidget(replace_btn)
        header.addWidget(remove_btn)
        layout.addLayout(header)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(120)
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        form.addWidget(QLabel("Etiqueta"), 0, 0)
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("Título opcional del bloque")
        form.addWidget(self.label_edit, 0, 1)
        form.addWidget(QLabel("Archivo"), 1, 0)
        self.path_label = QLabel("")
        self.path_label.setWordWrap(True)
        self.path_label.setObjectName("muted")
        form.addWidget(self.path_label, 1, 1)
        layout.addLayout(form)

    def _kind_title(self) -> str:
        return {
            "image": "Imagen",
            "video": "Vídeo",
            "document": "Documento",
        }.get(self.block_type, "Archivo")

    def set_data(self, data: dict) -> None:
        self.label_edit.setText(str(data.get("label") or ""))
        path = str(data.get("path") or "")
        self.path_label.setText(path)
        self._update_preview(path)

    def _update_preview(self, path: str) -> None:
        resolved = _resolve_press_path(path) if path else Path()
        if self.block_type == "image" and path and resolved.exists():
            pix = QPixmap(str(resolved))
            if not pix.isNull():
                self.preview.setPixmap(pix.scaledToWidth(360, Qt.TransformationMode.SmoothTransformation))
                return
        self.preview.setPixmap(QPixmap())
        if self.block_type == "video":
            self.preview.setText("Vídeo adjunto")
        elif self.block_type == "document":
            self.preview.setText("Documento adjunto")
        else:
            self.preview.setText("Archivo adjunto")

    def block_data(self) -> dict:
        return {
            "type": self.block_type,
            "path": self.path_label.text().strip(),
            "label": self.label_edit.text().strip(),
        }


class PressCarouselBlockWidget(QFrame):
    activated = pyqtSignal(object)
    remove_requested = pyqtSignal(object)
    replace_requested = pyqtSignal(object)

    def __init__(self, data: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("pressBlock")
        self.setProperty("kind", "carousel")
        self.items: list[dict] = []
        self.index = 0
        self._player = None
        self._audio = None
        self._build_ui()
        if data:
            self.set_data(data)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self)
        super().mousePressEvent(event)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self.kind_label = QLabel("Carrusel de imágenes")
        self.kind_label.setObjectName("status")
        header.addWidget(self.kind_label)
        header.addStretch()
        replace_btn = QPushButton("Cambiar")
        replace_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        replace_btn.clicked.connect(lambda: self.replace_requested.emit(self))
        remove_btn = QPushButton("Eliminar")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        header.addWidget(replace_btn)
        header.addWidget(remove_btn)
        layout.addLayout(header)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Título del carrusel")
        layout.addWidget(self.title_edit)

        self.viewer_stack = QStackedWidget()
        self.viewer_stack.setMinimumHeight(220)
        self.viewer_stack.setStyleSheet("background: rgba(7, 16, 25, 180); border-radius: 10px;")
        self.image_label = QLabel("Sin imágenes")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setWordWrap(True)
        self.viewer_stack.addWidget(self.image_label)
        layout.addWidget(self.viewer_stack)

        nav = QHBoxLayout()
        self.prev_btn = QPushButton("Anterior")
        self.prev_btn.clicked.connect(self._previous)
        self.next_btn = QPushButton("Siguiente")
        self.next_btn.clicked.connect(self._next)
        self.counter_label = QLabel("")
        self.counter_label.setObjectName("muted")
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.next_btn)
        nav.addStretch()
        nav.addWidget(self.counter_label)
        layout.addLayout(nav)

        self._gallery = QHBoxLayout()
        meta = QGridLayout()
        meta.setHorizontalSpacing(10)
        meta.setVerticalSpacing(8)
        meta.addWidget(QLabel("Etiquetas"), 0, 0)
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setObjectName("muted")
        meta.addWidget(self.summary_label, 0, 1)
        layout.addLayout(meta)

    def set_data(self, data: dict) -> None:
        self.title_edit.setText(str(data.get("label") or "Carrusel"))
        self.items = [dict(item) for item in list(data.get("items", []) or [])]
        self.index = 0
        self._show_current()

    def block_data(self) -> dict:
        return {
            "type": "carousel",
            "label": self.title_edit.text().strip(),
            "items": [
                {
                    "path": str(item.get("path", "")).strip(),
                    "label": str(item.get("label", "")).strip(),
                }
                for item in self.items
                if str(item.get("path", "")).strip()
            ],
        }

    def _current_item(self) -> dict | None:
        if not self.items:
            return None
        self.index %= len(self.items)
        return self.items[self.index]

    def _show_current(self) -> None:
        item = self._current_item()
        if item is None:
            self.counter_label.setText("0/0")
            self.image_label.setText("Sin imágenes")
            self.viewer_stack.setCurrentWidget(self.image_label)
            self.summary_label.setText("")
            return
        path = str(item.get("path", ""))
        label = str(item.get("label") or Path(path).stem or "Imagen")
        self.summary_label.setText(", ".join([str(entry.get("label") or Path(str(entry.get("path", ""))).stem) for entry in self.items]))
        self.counter_label.setText(f"{self.index + 1}/{len(self.items)} · {label}")
        resolved = _resolve_press_path(path)
        if resolved.exists():
            pix = QPixmap(str(resolved))
            if not pix.isNull():
                self.image_label.setPixmap(pix.scaled(
                    self.viewer_stack.size().expandedTo(QSize(700, 260)),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
                self.viewer_stack.setCurrentWidget(self.image_label)
                return
        self.image_label.setText("No se pudo cargar la imagen.")
        self.viewer_stack.setCurrentWidget(self.image_label)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.items and self.viewer_stack.currentWidget() == self.image_label and self.image_label.pixmap() is not None:
            self._show_current()

    def _previous(self) -> None:
        if self.items:
            self.index = (self.index - 1) % len(self.items)
            self._show_current()

    def _next(self) -> None:
        if self.items:
            self.index = (self.index + 1) % len(self.items)
            self._show_current()


class PressBlockEditor(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.current_block: QWidget | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(0, 0, 0, 0)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        for label, kind in [("Texto", "text"), ("Imagen", "image"), ("Carrusel", "carousel"), ("Vídeo", "video"), ("Documento", "document")]:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, media_kind=kind: self.insert_media(media_kind))
            tools.addWidget(btn)
        tools.addStretch()
        root.addLayout(tools)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        self.container = QWidget()
        self.blocks_layout = QVBoxLayout(self.container)
        self.blocks_layout.setContentsMargins(0, 0, 0, 0)
        self.blocks_layout.setSpacing(12)
        self.blocks_layout.addStretch()
        scroll.setWidget(self.container)
        root.addWidget(scroll)
        self.scroll_area = scroll
        self.ensure_text_block()

    def clear(self) -> None:
        while self.blocks_layout.count():
            item = self.blocks_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self.blocks_layout.addStretch()
        self.current_block = None

    def ensure_text_block(self) -> None:
        if self.count_content_blocks() == 0:
            self.add_text_block("", focus=True)

    def count_content_blocks(self) -> int:
        count = 0
        for index in range(self.blocks_layout.count()):
            item = self.blocks_layout.itemAt(index)
            if item and item.widget() is not None:
                count += 1
        return count

    def _insert_widget_before_stretch(self, widget: QWidget, index: int | None = None) -> None:
        stretch_index = max(0, self.blocks_layout.count() - 1)
        if index is None or index >= stretch_index:
            self.blocks_layout.insertWidget(stretch_index, widget)
        else:
            self.blocks_layout.insertWidget(index, widget)

    def add_text_block(self, html: str = "", focus: bool = False, index: int | None = None) -> PressTextBlockWidget:
        widget = PressTextBlockWidget(html)
        widget.activated.connect(self._set_current)
        widget.remove_requested.connect(self.remove_block)
        widget.insert_requested.connect(self.insert_media)
        self._insert_widget_before_stretch(widget, index)
        if focus:
            widget.editor.setFocus()
        return widget

    def add_media_block(self, block_type: str, data: dict, index: int | None = None) -> QWidget:
        if block_type == "carousel":
            widget = PressCarouselBlockWidget(data)
        else:
            widget = PressMediaBlockWidget(block_type, data)
        widget.activated.connect(self._set_current)
        widget.remove_requested.connect(self.remove_block)
        widget.replace_requested.connect(self.replace_media)
        self._insert_widget_before_stretch(widget, index)
        return widget

    def set_blocks(self, blocks: list[dict]) -> None:
        self.clear()
        if not blocks:
            self.add_text_block("")
            return
        for block in blocks:
            block_type = str(block.get("type", "")).strip().lower()
            if block_type == "text":
                self.add_text_block(str(block.get("html") or ""), focus=False)
            elif block_type == "carousel":
                self.add_media_block("carousel", block)
            else:
                self.add_media_block(block_type or "document", block)
        self.ensure_text_block()

    def blocks(self) -> list[dict]:
        result: list[dict] = []
        for index in range(self.blocks_layout.count()):
            item = self.blocks_layout.itemAt(index)
            widget = item.widget() if item else None
            if isinstance(widget, PressTextBlockWidget):
                text = widget.plain_text().strip()
                html = widget.html() if text else ""
                if not text and not html.strip():
                    continue
                result.append({"type": "text", "html": html, "plain": text})
            elif isinstance(widget, PressCarouselBlockWidget):
                block = widget.block_data()
                if block["items"]:
                    result.append(block)
            elif isinstance(widget, PressMediaBlockWidget):
                block = widget.block_data()
                if block.get("path"):
                    result.append(block)
        return result

    def _set_current(self, widget: QWidget) -> None:
        self.current_block = widget

    def _widget_index(self, widget: QWidget) -> int:
        for index in range(self.blocks_layout.count()):
            item = self.blocks_layout.itemAt(index)
            if item and item.widget() is widget:
                return index
        return max(0, self.blocks_layout.count() - 1)

    def remove_block(self, widget: QWidget) -> None:
        index = self._widget_index(widget)
        widget.setParent(None)
        widget.deleteLater()
        if self.count_content_blocks() == 0:
            self.add_text_block("", focus=True)
        elif isinstance(widget, PressTextBlockWidget) and self.count_content_blocks() == 1:
            self.add_text_block("", focus=True)
        else:
            self.current_block = None

    def replace_media(self, widget: QWidget) -> None:
        if isinstance(widget, PressCarouselBlockWidget):
            files, _ = QFileDialog.getOpenFileNames(
                self,
                "Reemplazar carrusel",
                str(BASE_DIR),
                "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;Todos los archivos (*)",
            )
            if files:
                widget.set_data({
                    "label": widget.title_edit.text(),
                    "items": [{"path": file_name, "label": Path(file_name).stem} for file_name in files],
                })
            return
        media_type = getattr(widget, "block_type", "document")
        filters = {
            "image": "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;Todos los archivos (*)",
            "video": "Vídeos (*.mp4 *.mov *.mkv *.webm *.avi);;Todos los archivos (*)",
        }.get(media_type, "Todos los archivos (*)")
        file_name, _ = QFileDialog.getOpenFileName(self, "Seleccionar archivo", str(BASE_DIR), filters)
        if file_name:
            widget.set_data({"path": file_name, "label": Path(file_name).stem})

    def _insert_after_current(self, widget: QWidget) -> int:
        if self.current_block is None:
            return max(0, self.blocks_layout.count() - 1)
        index = self._widget_index(self.current_block)
        self.blocks_layout.insertWidget(index + 1, widget)
        return index + 1

    def _split_text_block(self, block: PressTextBlockWidget) -> int:
        before, after = block.split_at_cursor()
        index = self._widget_index(block)
        block.set_html(before)
        if after.strip():
            after_block = PressTextBlockWidget("")
            after_block.set_html(after)
            after_block.activated.connect(self._set_current)
            after_block.remove_requested.connect(self.remove_block)
            after_block.insert_requested.connect(self.insert_media)
            self.blocks_layout.insertWidget(index + 1, after_block)
        return index + 1

    def insert_media(self, media_kind: str) -> None:
        insert_index = None
        if isinstance(self.current_block, PressTextBlockWidget):
            insert_index = self._split_text_block(self.current_block)
        elif self.current_block is not None:
            insert_index = self._widget_index(self.current_block) + 1
        if media_kind == "text":
            self.add_text_block("", focus=True, index=insert_index)
            return

        if media_kind == "carousel":
            files, _ = QFileDialog.getOpenFileNames(
                self,
                "Seleccionar imágenes del carrusel",
                str(BASE_DIR),
                "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;Todos los archivos (*)",
            )
            if not files:
                return
            data = {"label": "Carrusel", "items": [{"path": file_name, "label": Path(file_name).stem} for file_name in files]}
            self.add_media_block("carousel", data, index=insert_index)
            return

        filters = {
            "image": "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;Todos los archivos (*)",
            "video": "Vídeos (*.mp4 *.mov *.mkv *.webm *.avi);;Todos los archivos (*)",
            "document": "Documentos (*.pdf *.txt *.rtf *.doc *.docx *.odt *.md);;Todos los archivos (*)",
        }
        file_name, _ = QFileDialog.getOpenFileName(self, "Seleccionar archivo", str(BASE_DIR), filters.get(media_kind, "Todos los archivos (*)"))
        if not file_name:
            return
        data = {"path": file_name, "label": Path(file_name).stem}
        self.add_media_block(media_kind, data, index=insert_index)


class PressEditorDialog(QWidget):
    saved = pyqtSignal(dict)
    closed = pyqtSignal()

    def __init__(self, store: PressStore, note: dict | None = None, parent: QWidget | None = None):
        title = "Editar nota" if note else "Nueva nota"
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        
        # 1. AJUSTE DE TAMAÑO: Reducimos el ancho y limitamos el alto para que quepa en cualquier monitor.
        self.resize(950, 700) 
        self.setStyleSheet("QWidget { background: #07111d; }")
        
        # --- CÓDIGO PARA CENTRAR LA VENTANA EN LA PANTALLA ---
        screen = self.screen() if self.screen() else QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            # Calculamos la posición X e Y del centro
            x = screen_geo.x() + (screen_geo.width() - self.width()) // 2
            y = screen_geo.y() + (screen_geo.height() - self.height()) // 2
            self.move(x, y)
        # -----------------------------------------------------

        self.store = store
        self.note = dict(note or {})
        self.note_id = int(self.note.get("id", 0) or 0)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        
        self.panel = GlassPanel()
        self.panel.setObjectName("modalPanel")
        self.panel.setStyleSheet("""
            QFrame#modalPanel {
                background: #101d2c;
                border: 1px solid rgba(126, 164, 196, 90);
                border-radius: 14px;
            }
        """)
        outer.addWidget(self.panel)

        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(18, 16, 18, 18)
        panel_layout.setSpacing(14)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        title_label = QLabel(title)
        title_label.setObjectName("title")
        header.addWidget(title_label)
        header.addStretch()
        close_button = QPushButton("Cerrar")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.close)
        header.addWidget(close_button)
        panel_layout.addLayout(header)

        # 2. IMPLEMENTACIÓN DEL SCROLL AREA PARA EVITAR QUE CREZCA HACIA ABAJO
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        # Contenedor interno que llevará todos los campos del formulario
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        form_layout = QVBoxLayout(scroll_content)
        form_layout.setContentsMargins(0, 0, 4, 0) # Un pequeño margen derecho para el scrollbar
        form_layout.setSpacing(14)

        # --- A partir de aquí, añadimos los elementos a 'form_layout' en lugar de 'panel_layout' ---

        body_header = QLabel("Redacción de la nota")
        body_header.setObjectName("status")
        form_layout.addWidget(body_header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        self.title_edit = QLineEdit(self.note.get("title", ""))
        self.author_edit = QLineEdit(self.note.get("author", ""))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        current_date = QDate.currentDate()
        note_date = QDate.fromString(str(self.note.get("date", "")), "yyyy-MM-dd")
        self.date_edit.setDate(note_date if note_date.isValid() else current_date)
        self.importance_edit = QLineEdit(self.note.get("importance", ""))
        self.importance_edit.setPlaceholderText("Opcional")
        grid.addWidget(QLabel("Título"), 0, 0)
        grid.addWidget(self.title_edit, 0, 1)
        grid.addWidget(QLabel("Autor"), 0, 2)
        grid.addWidget(self.author_edit, 0, 3)
        grid.addWidget(QLabel("Fecha"), 1, 0)
        grid.addWidget(self.date_edit, 1, 1)
        grid.addWidget(QLabel("Importancia"), 1, 2)
        grid.addWidget(self.importance_edit, 1, 3)
        form_layout.addLayout(grid)

        self.main_image_path = str(self.note.get("main_image", "")).strip()
        self.main_image_crop = _press_crop_rect_from_payload(self.note.get("main_image_crop"))
        image_section = QHBoxLayout()
        image_section.setSpacing(12)
        image_box = QVBoxLayout()
        image_box.setSpacing(8)
        image_label = QLabel("Imagen principal")
        image_label.setObjectName("status")
        image_box.addWidget(image_label)
        self.main_image_preview = QLabel()
        self.main_image_preview.setMinimumSize(QSize(380, 214))
        self.main_image_preview.setMaximumHeight(240)
        self.main_image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_image_preview.setWordWrap(True)
        self.main_image_preview.setStyleSheet(
            "QLabel { background: rgba(7, 16, 25, 180); border: 1px solid rgba(126, 164, 196, 80); border-radius: 10px; color: #91a8bb; padding: 10px; }"
        )
        image_box.addWidget(self.main_image_preview, 1)
        image_btns = QHBoxLayout()
        select_image_btn = QPushButton("Seleccionar imagen")
        select_image_btn.clicked.connect(self._choose_main_image)
        clear_image_btn = QPushButton("Quitar imagen")
        clear_image_btn.clicked.connect(self._clear_main_image)
        image_btns.addWidget(select_image_btn)
        image_btns.addWidget(clear_image_btn)
        image_btns.addStretch()
        image_box.addLayout(image_btns)
        image_section.addLayout(image_box, 1)
        form_layout.addLayout(image_section)
        self._refresh_main_image_preview()

        self.editor = PressTextEdit()
        self.editor.setPlaceholderText("Escribe aquí la nota de prensa...")
        self.editor.setAcceptRichText(True)
        self.editor.setMinimumHeight(250) # Reducido ligeramente de 300 a 250 para optimizar espacio
        self.editor.reference_requested.connect(lambda: self._show_reference_menu(True))
        legacy_body = str(self.note.get("body_html", "")).strip()
        if not legacy_body and self.note.get("blocks"):
            legacy_body, _ = _press_legacy_body_and_attachments(list(self.note.get("blocks", []) or []))
        if legacy_body:
            self.editor.setHtml(legacy_body)
        form_layout.addWidget(self.editor)

        attachments_title = QLabel("Adjuntos al final")
        attachments_title.setObjectName("status")
        form_layout.addWidget(attachments_title)

        self.attachments = QListWidget()
        self.attachments.setMinimumHeight(120) # Reducido de 150 a 120
        self.attachments.setAlternatingRowColors(True)
        self.attachments.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._load_attachments()
        form_layout.addWidget(self.attachments)

        attachment_buttons = QHBoxLayout()
        add_attachment_btn = QPushButton("Añadir archivos")
        add_attachment_btn.clicked.connect(self._add_attachment)
        remove_attachment_btn = QPushButton("Eliminar archivo")
        remove_attachment_btn.clicked.connect(self._remove_attachment)
        reference_btn = QPushButton("@ Referencia")
        reference_btn.clicked.connect(lambda: self._show_reference_menu(False))
        attachment_buttons.addWidget(add_attachment_btn)
        attachment_buttons.addWidget(remove_attachment_btn)
        attachment_buttons.addWidget(reference_btn)
        attachment_buttons.addStretch()
        form_layout.addLayout(attachment_buttons)

        # Asignamos el contenedor al scroll area, y añadimos el scroll area al panel principal
        scroll.setWidget(scroll_content)
        panel_layout.addWidget(scroll, 1)

        # El footer (cancelar/guardar) se queda fuera del scroll para que siempre esté visible abajo fijado
        footer = QHBoxLayout()
        footer.addStretch()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.close)
        save_btn = QPushButton("Guardar")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save_note)
        footer.addWidget(cancel_btn)
        footer.addWidget(save_btn)
        panel_layout.addLayout(footer)

        fade_in(self.panel, 180)

    def _load_attachments(self) -> None:
        self.attachments.clear()
        for attachment in list(self.note.get("attachments", []) or []):
            path = str(attachment.get("path", "")).strip()
            if not path:
                continue
            label = str(attachment.get("label") or Path(path).stem or "Archivo").strip()
            kind = str(attachment.get("type") or _press_media_kind_for_path(_resolve_press_path(path))).strip().lower()
            item = QListWidgetItem(f"{label} · {kind.upper()}")
            item.setData(Qt.ItemDataRole.UserRole, {"path": path, "label": label, "type": kind})
            self.attachments.addItem(item)

    def _attachment_payloads(self) -> list[dict]:
        payloads: list[dict] = []
        for index in range(self.attachments.count()):
            item = self.attachments.item(index)
            payload = item.data(Qt.ItemDataRole.UserRole) or {}
            path = str(payload.get("path", "")).strip()
            if not path:
                continue
            payloads.append({
                "path": path,
                "label": str(payload.get("label") or Path(path).stem or "Archivo").strip(),
                "type": str(payload.get("type") or _press_media_kind_for_path(_resolve_press_path(path))).strip().lower(),
            })
        return payloads

    def _refresh_main_image_preview(self) -> None:
        path = str(self.main_image_path).strip()
        if not path:
            self.main_image_preview.setPixmap(QPixmap())
            self.main_image_preview.setText("Sin imagen principal")
            return
        resolved = _resolve_press_path(path)
        if not resolved.exists():
            self.main_image_preview.setPixmap(QPixmap())
            self.main_image_preview.setText("La imagen principal no se encontró.")
            return
        pix = QPixmap(str(resolved))
        if pix.isNull():
            self.main_image_preview.setPixmap(QPixmap())
            self.main_image_preview.setText("No se pudo cargar la imagen principal.")
            return
        pix = self._crop_main_image_pixmap(pix)
        self.main_image_preview.setText("")
        self.main_image_preview.setPixmap(
            pix.scaled(
                self.main_image_preview.size().expandedTo(QSize(380, 214)),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _choose_main_image(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar imagen principal",
            str(BASE_DIR),
            "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;Todos los archivos (*)",
        )
        if not file_name:
            return
        self.main_image_path = str(Path(file_name))
        self.main_image_crop = None
        self._refresh_main_image_preview()

    def _clear_main_image(self) -> None:
        self.main_image_path = ""
        self.main_image_crop = None
        self._refresh_main_image_preview()

    def _crop_main_image_pixmap(self, pixmap: QPixmap) -> QPixmap:
        return pixmap

    def _insert_attachment_reference(self, attachment: dict, replace_at: bool = False) -> None:
        path = str(attachment.get("path", "")).strip()
        label = str(attachment.get("label") or Path(path).stem or "Adjunto").strip()
        if not path:
            return
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        try:
            if replace_at:
                cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, 1)
                if cursor.selectedText() == "@":
                    cursor.removeSelectedText()
                else:
                    cursor.clearSelection()
            href = _press_encode_attachment_ref(path)
            link_html = f'<a href="{href}">@{html.escape(label)}</a>'
            cursor.insertHtml(link_html)
            cursor.insertText(" ")
        finally:
            cursor.endEditBlock()

    def _show_reference_menu(self, replace_at: bool = False) -> None:
        attachments = self._attachment_payloads()
        if not attachments:
            QMessageBox.information(self, APP_NAME, "Añade al menos un adjunto para poder referenciarlo.")
            return
        menu = QMenu(self)
        menu.setObjectName("pressNoteMenu")
        for attachment in attachments:
            action = QAction(f"@{attachment['label']}", self)
            action.triggered.connect(lambda _=False, payload=dict(attachment), replace_at=replace_at: self._insert_attachment_reference(payload, replace_at=replace_at))
            menu.addAction(action)
        pos = self.editor.viewport().mapToGlobal(self.editor.cursorRect().bottomLeft())
        menu.exec(pos)

    def _add_attachment(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Añadir adjuntos",
            str(BASE_DIR),
            "Todos los archivos (*)",
        )
        for file_name in files:
            if not file_name:
                continue
            path = Path(file_name)
            kind = _press_media_kind_for_path(path)
            label = path.stem
            item = QListWidgetItem(f"{label} · {kind.upper()}")
            item.setData(Qt.ItemDataRole.UserRole, {"path": str(path), "label": label, "type": kind})
            self.attachments.addItem(item)

    def _remove_attachment(self) -> None:
        row = self.attachments.currentRow()
        if row >= 0:
            self.attachments.takeItem(row)

    def _save_note(self) -> None:
        payload = self.result_payload()
        if not payload["title"]:
            QMessageBox.warning(self, APP_NAME, "El título es obligatorio.")
            return
        self.saved.emit(payload)
        self.close()

    def result_payload(self) -> dict:
        attachments = []
        for index in range(self.attachments.count()):
            item = self.attachments.item(index)
            payload = item.data(Qt.ItemDataRole.UserRole) or {}
            attachments.append({
                "path": str(payload.get("path", "")).strip(),
                "label": str(payload.get("label", "")).strip(),
                "type": str(payload.get("type", "")).strip().lower() or _press_media_kind_for_path(Path(str(payload.get("path", "")))),
            })
        return {
            "id": self.note_id,
            "title": self.title_edit.text().strip(),
            "author": self.author_edit.text().strip(),
            "date": self.date_edit.date().toString("yyyy-MM-dd"),
            "importance": self.importance_edit.text().strip(),
            "body_html": self.editor.toHtml().strip(),
            "main_image": self.main_image_path.strip(),
            "main_image_crop": _press_crop_payload_from_rect(self.main_image_crop),
            "attachments": attachments,
        }

    def closeEvent(self, event) -> None:
        self.closed.emit()
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "main_image_preview"):
            self._refresh_main_image_preview()


class PressNoteCard(QFrame):
    def __init__(self, note: dict, on_open, on_edit, on_delete, parent: QWidget | None = None):
        super().__init__(parent)
        self.note = note
        self.on_open = on_open
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.setObjectName("pressCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self._hovered = False
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(0)

        # Contenedor izquierdo: Contenido de texto
        text_widget = QWidget()
        text_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QVBoxLayout(text_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)

        # 1. TÍTULO
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)
        self.title_label = QLabel(str(self.note.get("title", "")) or "Sin título")
        self.title_label.setObjectName("transitionTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        top.addWidget(self.title_label, 1)
        layout.addLayout(top)

        # 2. IMPORTANCIA (Se muestra debajo del título si existe)
        importance = str(self.note.get("importance", "")).strip()
        if importance:
            chip = QLabel(importance)
            chip.setObjectName("stateChip")
            chip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            layout.addWidget(chip, alignment=Qt.AlignmentFlag.AlignLeft)

        # 3. CUERPO / RESUMEN DE LA NOTA
        summary = QLabel(self._summary_text())
        summary.setWordWrap(True)
        summary.setObjectName("muted")
        summary.setTextFormat(Qt.TextFormat.PlainText)
        summary.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        summary.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(summary)

        # 4. AUTOR Y FECHA (Ubicados ahora debajo del texto)
        meta = QLabel(self._meta_text())
        meta.setObjectName("muted")
        meta.setWordWrap(True)
        meta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(meta)

        outer.addWidget(text_widget, 1)

        # Contenedor derecho: Miniatura de la imagen si existe
        main_image = str(self.note.get("main_image", "")).strip()
        if main_image:
            resolved = _resolve_press_path(main_image)
            if resolved.exists():
                pix = QPixmap(str(resolved))
                if not pix.isNull():
                    THUMB_H = 72
                    aspect = pix.width() / max(1, pix.height())
                    thumb_w = max(48, int(THUMB_H * aspect))
                    thumb_w = min(thumb_w, 120)
                    thumb = pix.scaled(
                        thumb_w, THUMB_H,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    # Recorte centrado al tamaño exacto
                    if thumb.width() > thumb_w or thumb.height() > THUMB_H:
                        x_off = (thumb.width() - thumb_w) // 2
                        y_off = (thumb.height() - THUMB_H) // 2
                        thumb = thumb.copy(x_off, y_off, thumb_w, THUMB_H)
                    
                    thumb_label = QLabel()
                    thumb_label.setPixmap(thumb)
                    thumb_label.setFixedSize(thumb_w, THUMB_H)
                    thumb_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                    thumb_label.setStyleSheet(
                        "QLabel { border-radius: 8px; background: rgba(0,0,0,0); }"
                    )
                    thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    outer.addSpacing(14)
                    outer.addWidget(thumb_label, 0, Qt.AlignmentFlag.AlignVCenter)

    def _meta_text(self) -> str:
        author = str(self.note.get("author", "")).strip() or "Sin autor"
        date = self.note.get("date", "")
        try:
            date_obj = QDate.fromString(str(date), "yyyy-MM-dd")
            date_label = date_obj.toString("dd/MM/yyyy") if date_obj.isValid() else str(date)
        except Exception:
            date_label = str(date)
        return f"{author} · {date_label}"

    def _summary_text(self) -> str:
        blocks = list(self.note.get("blocks", []) or [])
        if blocks:
            return _press_summary_from_blocks(blocks)
        body_html = str(self.note.get("body_html", "")).strip()
        summary = str(self.note.get("summary", "")).strip()
        if summary:
            return _press_plain_text_from_html(summary)
        if body_html:
            return _press_summary_from_text(body_html)
        return "Sin resumen disponible."

    def _set_hovered(self, active: bool) -> None:
        if self._hovered == active:
            return
        self._hovered = active
        self.setProperty("hovered", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._set_hovered(True)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._set_hovered(False)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_open(self.note)
        super().mousePressEvent(event)


class PressImageViewer(QFrame):
    def __init__(self, path: str, caption: str = "", crop: QRectF | None = None, max_width: int = 380, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("pressBlock")
        self._crop = crop
        self._max_width = max_width
        self._zoom = 1.0
        self._base_pixmap = QPixmap(str(_resolve_press_path(path)))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setWordWrap(True)
        self.image.setMinimumHeight(180)
        self.image.setMouseTracking(True)
        self.image.setStyleSheet("QLabel { background: rgba(7, 16, 25, 80); border-radius: 10px; }")
        self.image.installEventFilter(self)
        self._update_pixmap()
        layout.addWidget(self.image)
        if caption:
            cap = QLabel(caption)
            cap.setObjectName("muted")
            cap.setWordWrap(True)
            layout.addWidget(cap)

    def _apply_crop(self, pixmap: QPixmap) -> QPixmap:
        return _press_crop_image(pixmap, self._crop)

    def _update_pixmap(self) -> None:
        if self._base_pixmap.isNull():
            self.image.setPixmap(QPixmap())
            self.image.setText("No se pudo cargar la imagen.")
            return
        pix = self._apply_crop(self._base_pixmap)
        target_width = max(220, int(self._max_width * self._zoom))
        self.image.setText("")
        self.image.setPixmap(
            pix.scaledToWidth(target_width, Qt.TransformationMode.SmoothTransformation)
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_pixmap()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta > 0:
            self._zoom = min(2.5, self._zoom * 1.12)
            self._update_pixmap()
            event.accept()
        elif delta < 0:
            self._zoom = max(0.5, self._zoom / 1.12)
            self._update_pixmap()
            event.accept()
        else:
            super().wheelEvent(event)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.image and event.type() == QEvent.Type.Wheel:
            self.wheelEvent(event)
            return True
        return super().eventFilter(obj, event)


class PressCarouselViewer(QFrame):
    def __init__(self, items: list[dict], title: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.items = list(items)
        self.index = 0
        self.setObjectName("pressBlock")
        self._build_ui(title)
        self._show_current()

    def _build_ui(self, title: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        if title:
            ttl = QLabel(title)
            ttl.setObjectName("status")
            layout.addWidget(ttl)
        self.viewer = QLabel()
        self.viewer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewer.setMinimumHeight(220)
        self.viewer.setWordWrap(True)
        layout.addWidget(self.viewer)
        nav = QHBoxLayout()
        self.prev_btn = QPushButton("Anterior")
        self.prev_btn.clicked.connect(self._previous)
        self.next_btn = QPushButton("Siguiente")
        self.next_btn.clicked.connect(self._next)
        self.counter = QLabel("")
        self.counter.setObjectName("muted")
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.next_btn)
        nav.addStretch()
        nav.addWidget(self.counter)
        layout.addLayout(nav)

    def _show_current(self) -> None:
        if not self.items:
            self.counter.setText("0/0")
            self.viewer.setText("Sin imágenes")
            return
        self.index %= len(self.items)
        item = self.items[self.index]
        path = str(item.get("path", ""))
        label = str(item.get("label") or Path(path).stem or "Imagen")
        self.counter.setText(f"{self.index + 1}/{len(self.items)} · {label}")
        pix = QPixmap(str(_resolve_press_path(path)))
        if pix.isNull():
            self.viewer.setText("No se pudo cargar la imagen.")
            return
        self.viewer.setPixmap(pix.scaledToWidth(760, Qt.TransformationMode.SmoothTransformation))

    def _previous(self) -> None:
        if self.items:
            self.index = (self.index - 1) % len(self.items)
            self._show_current()

    def _next(self) -> None:
        if self.items:
            self.index = (self.index + 1) % len(self.items)
            self._show_current()


class PressVideoViewer(QFrame):
    def __init__(self, path: str, caption: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("pressBlock")
        self._player = None
        self._audio = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        if caption:
            cap = QLabel(caption)
            cap.setObjectName("status")
            layout.addWidget(cap)
        if _MULTIMEDIA_AVAILABLE:
            self.video_view = QVideoWidget()
            self.video_view.setMinimumHeight(280)
            layout.addWidget(self.video_view)
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
            self._player.setVideoOutput(self.video_view)
            self._player.setSource(QUrl.fromLocalFile(str(_resolve_press_path(path).resolve())))
            self._player.play()
        else:
            label = QLabel("El reproductor de vídeo no está disponible en este entorno.")
            label.setWordWrap(True)
            layout.addWidget(label)
            open_btn = QPushButton("Abrir externamente")
            open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(_resolve_press_path(path).resolve()))))
            layout.addWidget(open_btn, alignment=Qt.AlignmentFlag.AlignLeft)

    def stop(self) -> None:
        if self._player is not None:
            self._player.stop()


class PressDocumentViewer(QFrame):
    def __init__(self, path: str, caption: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("pressBlock")
        self._pdf = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        if caption:
            cap = QLabel(caption)
            cap.setObjectName("status")
            layout.addWidget(cap)
        resolved = _resolve_press_path(path)
        mime_type, _ = mimetypes.guess_type(str(resolved))
        if resolved.suffix.lower() == ".pdf" and _PDF_AVAILABLE:
            self.viewer = QPdfView()
            self.viewer.setMinimumHeight(320)
            layout.addWidget(self.viewer)
            self._pdf = QPdfDocument(self)
            self._pdf.load(str(resolved))
            self.viewer.setDocument(self._pdf)
        elif resolved.suffix.lower() in {".txt", ".md", ".log", ".json", ".csv", ".rtf", ".py"} or (mime_type or "").startswith("text/"):
            text_view = QTextEdit()
            text_view.setReadOnly(True)
            try:
                text_view.setPlainText(resolved.read_text(encoding="utf-8"))
            except Exception:
                try:
                    text_view.setPlainText(resolved.read_text(encoding="latin-1"))
                except Exception:
                    text_view.setPlainText("No se pudo leer el documento.")
            text_view.setMinimumHeight(320)
            layout.addWidget(text_view)
        else:
            label = QLabel("Vista integrada no disponible para este formato.")
            label.setWordWrap(True)
            layout.addWidget(label)
            open_btn = QPushButton("Abrir externamente")
            open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved.resolve()))))
            layout.addWidget(open_btn, alignment=Qt.AlignmentFlag.AlignLeft)


class PressAttachmentWindow(QMainWindow):
    def __init__(self, attachment: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.attachment = dict(attachment)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle(str(self.attachment.get("label") or "Adjunto"))
        self.setWindowIcon(QIcon(str(LOGO_PATH_CORT if LOGO_PATH_CORT.exists() else LOGO_PATH)))
        self.setMinimumSize(900, 620)
        self.resize(1100, 760)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel(str(self.attachment.get("label") or "Adjunto"))
        title.setObjectName("transitionTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        meta = QLabel(self._meta_text())
        meta.setObjectName("muted")
        meta.setWordWrap(True)
        layout.addWidget(meta)

        self.viewer: QWidget | None = None
        self._build_viewer(layout)
        self.setCentralWidget(central)

    def _meta_text(self) -> str:
        path = str(self.attachment.get("path", "")).strip()
        att_type = str(self.attachment.get("type", "")).strip().lower()
        return f"{att_type or 'archivo'} · {Path(path).name or 'sin nombre'}"

    def _build_viewer(self, layout: QVBoxLayout) -> None:
        path = str(self.attachment.get("path", "")).strip()
        att_type = str(self.attachment.get("type", "")).strip().lower()
        label = str(self.attachment.get("label", "")) or Path(path).stem or "Adjunto"

        if att_type == "image":
            self.viewer = PressImageViewer(path, label)
            layout.addWidget(self.viewer, 1)
        elif att_type == "video":
            self.viewer = PressVideoViewer(path, label)
            layout.addWidget(self.viewer, 1)
        elif att_type == "document":
            self.viewer = PressDocumentViewer(path, label)
            layout.addWidget(self.viewer, 1)
        elif att_type == "carousel":
            items = list(self.attachment.get("items", []) or [])
            self.viewer = PressCarouselViewer(items, label)
            layout.addWidget(self.viewer, 1)
        else:
            fallback = PressDocumentViewer(path, label)
            self.viewer = fallback
            layout.addWidget(fallback, 1)

    def closeEvent(self, event) -> None:
        viewer = self.viewer
        if isinstance(viewer, PressVideoViewer):
            viewer.stop()
        super().closeEvent(event)


class PressIntroScreen(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._finish_callback = None
        self.timer = QTimer(self)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        layout.addStretch()

        self.logo = LogoLabel(QSize(460, 170))
        self.logo.setMinimumHeight(170)
        layout.addWidget(self.logo, alignment=Qt.AlignmentFlag.AlignCenter)

        self.spinner = SpinnerWidget(74)
        layout.addWidget(self.spinner, alignment=Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Notas de Prensa")
        title.setObjectName("transitionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Sincronizando archivo editorial")
        subtitle.setObjectName("muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addStretch()

    def start(self, finished_callback) -> None:
        self._finish_callback = finished_callback
        QTimer.singleShot(1400, self._finish)

    def _finish(self) -> None:
        if self._finish_callback is not None:
            self._finish_callback()


class PressReaderScreen(QWidget):
    back_clicked = pyqtSignal()

    def __init__(self, store: PressStore, on_edit, on_delete, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.current_note_id: int | None = None
        self._video_widgets: list[PressVideoViewer] = []
        self._attachment_windows: list[PressAttachmentWindow] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(0)

        self.panel = GlassPanel()
        self.panel.setObjectName("pressPanel")
        self.panel.setStyleSheet("""
            QFrame#pressPanel {
                background: #101d2c;
                border: 1px solid rgba(126, 164, 196, 90);
                border-radius: 14px;
            }
        """)
        root.addWidget(self.panel)

        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(18, 16, 18, 18)
        panel_layout.setSpacing(14)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        back_btn = QPushButton("← Lista")
        back_btn.setObjectName("btnBack")
        back_btn.clicked.connect(self.back_clicked.emit)
        header.addWidget(back_btn)
        header.addStretch()

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)
        self.title_label = QLabel("Notas de Prensa")
        self.title_label.setObjectName("title")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel(" ")
        subtitle.setObjectName("muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_box.addWidget(self.title_label)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        self.menu_button = QToolButton()
        self.menu_button.setText("⋮")
        self.menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.menu_button.setAutoRaise(True)
        self.menu_button.setObjectName("pressMenuButton")
        self.menu_button.setFixedSize(34, 34)
        header.addWidget(self.menu_button, 0, alignment=Qt.AlignmentFlag.AlignTop)
        header.addStretch()

        panel_layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(14)
        self.scroll.setWidget(self.content)
        panel_layout.addWidget(self.scroll, 1)

    def show_note(self, note: dict) -> None:
        self.current_note_id = int(note.get("id", 0) or 0)
        self._rebuild_menu(note)
        self.title_label.setText(str(note.get("title", "")) or "Sin título")
        self._clear_content()

        body = QTextBrowser()
        body.setOpenExternalLinks(False)
        body.setOpenLinks(False)
        body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body.setStyleSheet(
            "QTextBrowser { background: transparent; border: none; color: #dce9f6; }"
            "QTextBrowser a { color: #4da3ff; text-decoration: none; }"
            "QTextBrowser a:hover { text-decoration: underline; }"
        )
        body.document().documentLayout().documentSizeChanged.connect(
            lambda *args: body.setFixedHeight(int(body.document().size().height()) + 15)
        )

        main_image = str(note.get("main_image", "")).strip()
        main_image_html = ""
        if main_image:
            resolved = _resolve_press_path(main_image)
            if resolved.exists():
                pix = QPixmap(str(resolved))
                if not pix.isNull():
                    w = pix.width() // 2
                    h = pix.height() // 2
                    max_w = 420
                    if w > max_w:
                        scale = max_w / w
                        w = max_w
                        h = max(1, int(h * scale))
                    
                    # Create padded pixmap to act as margins: right = 28px, bottom = 20px
                    margin_right = 28
                    margin_bottom = 20
                    padded_pix = QPixmap(w + margin_right, h + margin_bottom)
                    padded_pix.fill(QColor(0, 0, 0, 0))
                    
                    scaled_pix = pix.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    painter = QPainter(padded_pix)
                    painter.drawPixmap(0, 0, scaled_pix)
                    painter.end()
                    
                    img_ref = f"main_image_{self.current_note_id}"
                    body.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(img_ref), padded_pix)
                    main_image_html = f'<img src="{img_ref}" align="left" width="{w + margin_right}" height="{h + margin_bottom}">'

        importance = str(note.get("importance", "")).strip()
        if importance:
            chip = QLabel(importance)
            chip.setObjectName("stateChip")
            self.content_layout.addWidget(chip, alignment=Qt.AlignmentFlag.AlignLeft)
        body_html = str(note.get("body_html", "")).strip()
        if not body_html and note.get("blocks"):
            body_html, _ = _press_legacy_body_and_attachments(list(note.get("blocks", []) or []))
        if main_image_html:
            body_html = main_image_html + body_html
        body.setHtml(body_html or "<p>Sin contenido.</p>")
        body.anchorClicked.connect(lambda url, payload=note: self._open_body_anchor(payload, url))
        self.content_layout.addWidget(body)

        attachments = list(note.get("attachments", []) or [])
        if not attachments and note.get("blocks"):
            _, attachments = _press_legacy_body_and_attachments(list(note.get("blocks", []) or []))
        if attachments:
            attachments_title = QLabel("Adjuntos")
            attachments_title.setObjectName("status")
            self.content_layout.addWidget(attachments_title)
            attachments_wrap = QWidget()
            attachments_wrap_layout = QVBoxLayout(attachments_wrap)
            attachments_wrap_layout.setContentsMargins(0, 0, 0, 0)
            attachments_wrap_layout.setSpacing(10)
            attachment_icons = {"image": "🖼", "video": "🎬", "document": "📄"}
            for attachment in attachments:
                path = str(attachment.get("path", "")).strip()
                label = str(attachment.get("label", "")) or Path(path).stem or "Adjunto"
                file_name = Path(path).name if path else "Adjunto"
                kind = str(attachment.get("type", "")).strip().lower()
                icon = attachment_icons.get(kind, "📎")
                btn = QPushButton(f"{icon}   {file_name}")
                btn.setObjectName("pressAttachmentButton")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setToolTip(f"Abrir {label}")
                btn.setMinimumHeight(42)
                btn.clicked.connect(lambda _=False, payload=dict(attachment): self._open_attachment(payload))
                attachments_wrap_layout.addWidget(btn)
            self.content_layout.addWidget(attachments_wrap)
        meta = QLabel(self._meta_text(note))
        meta.setObjectName("muted")
        meta.setWordWrap(True)
        meta.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.content_layout.addWidget(meta)
        self.content_layout.addStretch()
        self.scroll.verticalScrollBar().setValue(0)

    def _meta_text(self, note: dict) -> str:
        author = str(note.get("author", "")).strip() or "Sin autor"
        date = str(note.get("date", "")).strip()
        date_obj = QDate.fromString(date, "yyyy-MM-dd")
        date_label = date_obj.toString("dd/MM/yyyy") if date_obj.isValid() else date
        return f"{author} · {date_label}"

    def _clear_content(self) -> None:
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                if isinstance(widget, PressVideoViewer):
                    widget.stop()
                widget.setParent(None)
        self._video_widgets.clear()
        for window in list(self._attachment_windows):
            if window is not None:
                window.close()
        self._attachment_windows.clear()

    def _open_attachment(self, attachment: dict) -> None:
        window = PressAttachmentWindow(attachment, parent=self.window())
        window.destroyed.connect(lambda _=None, ref=window: self._forget_attachment_window(ref))
        self._attachment_windows.append(window)
        self._center_window(window)
        window.show()
        window.raise_()
        window.activateWindow()

    def _find_attachment_for_path(self, note: dict, path: str) -> dict | None:
        target = _resolve_press_path(path)
        candidates = list(note.get("attachments", []) or [])
        for attachment in candidates:
            raw_path = str(attachment.get("path", "")).strip()
            if not raw_path:
                continue
            if raw_path == path:
                return dict(attachment)
            if _resolve_press_path(raw_path) == target:
                return dict(attachment)
        main_image = str(note.get("main_image", "")).strip()
        if main_image and _resolve_press_path(main_image) == target:
            return {
                "path": main_image,
                "label": Path(main_image).stem or "Imagen principal",
                "type": "image",
            }
        if target.exists():
            return {
                "path": path,
                "label": target.stem or "Adjunto",
                "type": _press_media_kind_for_path(target),
            }
        return None

    def _open_body_anchor(self, note: dict, url: QUrl) -> None:
        path = _press_decode_attachment_ref(url.toString())
        if not path:
            return
        attachment = self._find_attachment_for_path(note, path)
        if attachment is not None:
            self._open_attachment(attachment)

    def _forget_attachment_window(self, window: PressAttachmentWindow) -> None:
        self._attachment_windows = [item for item in self._attachment_windows if item is not window]

    def _center_window(self, window: QWidget) -> None:
        screen = self.window().screen() if self.window() is not None else QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        size = window.frameGeometry()
        x = geo.x() + (geo.width() - size.width()) // 2
        y = geo.y() + (geo.height() - size.height()) // 2
        window.move(max(geo.x(), x), max(geo.y(), y))

    def _rebuild_menu(self, note: dict) -> None:
        menu = QMenu(self)
        menu.setObjectName("pressNoteMenu")
        edit_action = QAction("Editar", self)
        delete_action = QAction("Eliminar", self)
        edit_action.triggered.connect(lambda: self.on_edit(note))
        delete_action.triggered.connect(lambda: self.on_delete(note))
        menu.addAction(edit_action)
        menu.addAction(delete_action)
        self.menu_button.setMenu(menu)


class PressListScreen(QWidget):
    back_clicked = pyqtSignal()

    def __init__(self, store: PressStore, on_open_note, on_create_note, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.on_open_note = on_open_note
        self.on_create_note = on_create_note
        self.current_query = ""
        self.current_page = 1
        self.page_size = 10
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(0)

        self.panel = GlassPanel()
        self.panel.setObjectName("pressPanel")
        self.panel.setStyleSheet("""
            QFrame#pressPanel {
                background: #101d2c;
                border: 1px solid rgba(126, 164, 196, 90);
                border-radius: 14px;
            }
        """)
        root.addWidget(self.panel)

        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(18, 16, 18, 18)
        panel_layout.setSpacing(14)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        header.addStretch()
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)
        title = QLabel("Notas de Prensa")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel(" ")
        subtitle.setObjectName("muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        header.addStretch()

        panel_layout.addLayout(header)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por título")
        self.search.setMaximumWidth(560)
        self.search.textChanged.connect(self._on_search_changed)
        search_row = QHBoxLayout()
        search_row.addStretch()
        search_row.addWidget(self.search)
        search_row.addStretch()
        panel_layout.addLayout(search_row)

        self.count_label = QLabel("")
        self.count_label.setObjectName("muted")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel_layout.addWidget(self.count_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        self.scroll_content = QWidget()
        self.cards_layout = QVBoxLayout(self.scroll_content)
        self.cards_layout.setContentsMargins(0, 4, 0, 4)
        self.cards_layout.setSpacing(18)
        self.scroll.setWidget(self.scroll_content)
        panel_layout.addWidget(self.scroll, 1)

        self.empty_label = QLabel("No se han encontrado coincidencias.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setObjectName("muted")
        self.cards_layout.addWidget(self.empty_label)

        pagination = QHBoxLayout()
        pagination.setSpacing(10)
        self.page_info = QLabel("Página 1/1")
        self.page_info.setObjectName("muted")
        self.prev_btn = QPushButton("Anterior")
        self.next_btn = QPushButton("Siguiente")
        self.prev_btn.clicked.connect(self._previous_page)
        self.next_btn.clicked.connect(self._next_page)
        pagination.addWidget(self.prev_btn)
        pagination.addWidget(self.next_btn)
        pagination.addWidget(self.page_info)
        pagination.addStretch()
        panel_layout.addLayout(pagination)

        self.fab = QPushButton("+")
        self.fab.setObjectName("pressFab")
        self.fab.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fab.setFixedSize(58, 58)
        self.fab.clicked.connect(self.on_create_note)
        self.fab.setParent(self)
        self.fab.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        margin = 28
        self.fab.move(self.width() - self.fab.width() - margin, self.height() - self.fab.height() - margin)

    def refresh(self) -> None:
        notes = self.store.query_notes(self.current_query)
        total = len(notes)
        total_pages = max(1, math.ceil(total / self.page_size))
        self.current_page = min(max(1, self.current_page), total_pages)
        start = (self.current_page - 1) * self.page_size
        page_notes = notes[start:start + self.page_size]
        self._rebuild_cards(page_notes)
        self.count_label.setText(" ")
        self.page_info.setText(f"Página {self.current_page}/{total_pages}")
        self.empty_label.setVisible(total == 0)
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < total_pages)

    def _clear_layout(self, layout: QVBoxLayout | QHBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.setParent(None)
            elif child_layout is not None:
                self._clear_layout(child_layout)

    def _rebuild_cards(self, notes: list[dict]) -> None:
        self._clear_layout(self.cards_layout)
        if not notes:
            self.cards_layout.addWidget(self.empty_label)
            return
        for index, note in enumerate(notes):
            card = PressNoteCard(note, self.on_open_note, self._edit_note, self._delete_note)
            self.cards_layout.addWidget(card)
            if index < len(notes) - 1:
                separator = QFrame()
                separator.setObjectName("pressSeparator")
                separator.setFrameShape(QFrame.Shape.NoFrame)
                separator.setFixedHeight(1)
                separator.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                separator.setStyleSheet("background-color: rgba(126, 164, 196, 165); margin: 0px 18px;")
                self.cards_layout.addWidget(separator)
        self.cards_layout.addStretch()

    def _previous_page(self) -> None:
        if self.current_page > 1:
            self.current_page -= 1
            self.refresh()

    def _next_page(self) -> None:
        total = len(self.store.query_notes(self.current_query))
        total_pages = max(1, math.ceil(total / self.page_size))
        if self.current_page < total_pages:
            self.current_page += 1
            self.refresh()

    def _on_search_changed(self, text: str) -> None:
        self.current_query = text
        self.current_page = 1
        self.refresh()

    def _edit_note(self, note: dict) -> None:
        self.on_open_note(note, edit_mode=True)

    def _delete_note(self, note: dict) -> None:
        self.on_open_note(note, delete_mode=True)


class PressModuleScreen(QWidget):
    def __init__(self, on_back_to_command_center, parent: QWidget | None = None):
        super().__init__(parent)
        self.on_back_to_command_center = on_back_to_command_center
        self.store = PressStore()
        self._open_editors: list[PressEditorDialog] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        self.intro = PressIntroScreen()
        self.list_screen = PressListScreen(self.store, self._open_note, self._create_note)
        self.list_screen.back_clicked.connect(self.on_back_to_command_center)
        self.reader = PressReaderScreen(self.store, self._edit_note, self._delete_note)
        self.reader.back_clicked.connect(self._show_list)

        self.stack.addWidget(self.intro)
        self.stack.addWidget(self.list_screen)
        self.stack.addWidget(self.reader)
        self.stack.setCurrentWidget(self.list_screen)

        self.btn_back = QPushButton("← Volver", self)
        self.btn_back.setObjectName("btnBack")
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #FFFFFF;
                text-decoration: none;
                padding: 2px 4px;
            }
            QPushButton:hover {
                text-decoration: underline;
            }
        """)
        self.btn_back.clicked.connect(self.on_back_to_command_center)
        self.btn_back.adjustSize()
        self.btn_back.show()
        self.btn_back.raise_()
        self._position_back_button()

    def start(self) -> None:
        self.stack.setCurrentWidget(self.intro)
        self.intro.start(self._show_list)

    def refresh(self) -> None:
        self.list_screen.refresh()
        if self.reader.current_note_id is not None:
            note = self.store.get_note(self.reader.current_note_id)
            if note is not None:
                self.reader.show_note(note)

    # ------------------------------------------------------------------ #
    # Transición suave entre pantallas                                     #
    # ------------------------------------------------------------------ #
    def _press_fade_to(self, target_widget: QWidget, post_switch=None) -> None:
        """Realiza un fundido cruzado (fade-out → switch → fade-in) entre
        la pantalla actual del stack y *target_widget*.
        """
        current = self.stack.currentWidget()
        FADE_OUT_MS = 160
        FADE_IN_MS  = 220

        def _do_switch():
            self.stack.setCurrentWidget(target_widget)
            if post_switch:
                post_switch()
            # Fade-in del panel del widget entrante
            panel = getattr(target_widget, "panel", target_widget)
            effect = QGraphicsOpacityEffect(panel)
            panel.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"opacity", panel)
            anim.setDuration(FADE_IN_MS)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            panel._press_fade_anim_in = anim
            anim.finished.connect(lambda: panel.setGraphicsEffect(None))
            anim.start()

        if current is target_widget:
            _do_switch()
            return

        # Fade-out del panel saliente
        panel_out = getattr(current, "panel", current)
        effect_out = QGraphicsOpacityEffect(panel_out)
        panel_out.setGraphicsEffect(effect_out)
        anim_out = QPropertyAnimation(effect_out, b"opacity", panel_out)
        anim_out.setDuration(FADE_OUT_MS)
        anim_out.setStartValue(1.0)
        anim_out.setEndValue(0.0)
        anim_out.setEasingCurve(QEasingCurve.Type.InCubic)
        panel_out._press_fade_anim_out = anim_out
        anim_out.finished.connect(lambda: (panel_out.setGraphicsEffect(None), _do_switch()))
        anim_out.start()

    def _show_list(self) -> None:
        def _after():
            self.list_screen.refresh()
            self.reader.title_label.setText("Notas de Prensa")
            self._set_back_button_visible(True)
            self._position_back_button()
        self._press_fade_to(self.list_screen, _after)

    def _open_note(self, note: dict, edit_mode: bool = False, delete_mode: bool = False) -> None:
        note_id = int(note.get("id", 0) or 0)
        current = self.store.get_note(note_id)
        if current is None:
            self._show_list()
            return
        if delete_mode:
            self._delete_note(current)
            return
        if edit_mode:
            self._edit_note(current)
            return
        self.reader.show_note(current)
        def _after():
            self._set_back_button_visible(False)
            self._position_back_button()
        self._press_fade_to(self.reader, _after)

    def _create_note(self) -> None:
        self._open_editor()

    def _edit_note(self, note: dict) -> None:
        self._open_editor(note)

    def _open_editor(self, note: dict | None = None) -> None:
        for dialog in list(self._open_editors):
            if dialog is not None and dialog.isVisible():
                dialog.raise_()
                dialog.activateWindow()
                return
        dialog = PressEditorDialog(self.store, note, parent=None)
        dialog.saved.connect(lambda payload, source=dialog: self._on_editor_saved(source, payload))
        dialog.closed.connect(lambda source=dialog: self._release_editor(source))
        self._open_editors.append(dialog)
        self._position_editor(dialog)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _release_editor(self, dialog: PressEditorDialog) -> None:
        if dialog in self._open_editors:
            self._open_editors.remove(dialog)

    def _on_editor_saved(self, dialog: PressEditorDialog, payload: dict) -> None:
        saved_note = self.store.upsert_note(payload)
        self.refresh()
        if self.reader.current_note_id == int(saved_note.get("id", 0) or 0):
            self.reader.show_note(saved_note)
            self.stack.setCurrentWidget(self.reader)
            self._set_back_button_visible(False)
        else:
            self._show_list()
        self._release_editor(dialog)
        self._position_back_button()

    def _delete_note(self, note: dict) -> None:
        answer = QMessageBox.question(
            self,
            APP_NAME,
            "¿Eliminar esta nota de prensa?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.delete_note(int(note.get("id", 0) or 0))
        self.refresh()
        self._show_list()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_back_button()

    def _position_back_button(self) -> None:
        # Sube o baja este valor si quieres acercar o alejar el botón del borde inferior.
        margin = 0
        self.btn_back.adjustSize()
        self.btn_back.move(margin, self.height() - self.btn_back.height() - margin)
        self.btn_back.raise_()

    def _set_back_button_visible(self, visible: bool) -> None:
        self.btn_back.setVisible(visible)
        if visible:
            self.btn_back.raise_()

    def _position_editor(self, dialog: PressEditorDialog) -> None:
        screen = dialog.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        frame = dialog.frameGeometry()
        frame.moveCenter(available.center())
        dialog.move(frame.topLeft())


def _format_ksp_ut(seconds: float | None) -> str:
    if seconds is None:
        return "Desconocida"
    total = max(0, int(seconds))
    seconds_per_day = 6 * 60 * 60
    days_per_year = 426
    years = total // (seconds_per_day * days_per_year) + 1
    remaining = total % (seconds_per_day * days_per_year)
    day = remaining // seconds_per_day + 1
    remaining %= seconds_per_day
    hour = remaining // 3600
    minute = (remaining % 3600) // 60
    second = remaining % 60
    return f"Año {years} • Día {day:03d} • {hour:02d}:{minute:02d}:{second:02d}"


def _elide_text(text: str, width: int, font=None) -> str:
    if not text:
        return ""
    if font is None:
        font = QApplication.font()
    metrics = QFontMetrics(font)
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, width)


def _shorten_text(text: str, limit: int = 88) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 1)].rstrip() + "…"


def _normalize_key(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _load_json_file(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return default


def _save_json_file(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def _auto_group_for_altitude(alt_km: float) -> str:
    if alt_km < 900:
        return "LEO"
    if alt_km < 2800:
        return "MEO"
    if alt_km < 2900:
        return "GEO"
    return "EEO"


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _write_text_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _extract_ksp_install_root_from_log_text(text: str) -> Path | None:
    patterns = [
        r'([A-Za-z]:[\\/].*?[\\/](?:KSP_x64_Data|KSP_Data))[\\/]',
        r'([A-Za-z]:[\\/].*?[\\/](?:Spanish|English|Localization|KSP)[\\/](?:KSP_x64_Data|KSP_Data))[\\/]',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = Path(match.group(1)).resolve().parent
            if candidate.exists():
                return candidate
            return candidate
    return None


def _extract_current_save_name_from_log_text(text: str) -> str | None:
    matches = list(re.finditer(r"Game State (?:Loaded from|Saved to) saves[\\/](?P<save>[^\\/]+)[\\/](?:persistent|quicksave)", text, re.IGNORECASE))
    if not matches:
        return None
    return matches[-1].group("save").strip()


def _default_ksp_install_root() -> Path | None:
    for log_path in (KSP_PLAYER_LOG, KSP_PLAYER_PREV_LOG):
        if not log_path.exists():
            continue
        root = _extract_ksp_install_root_from_log_text(_read_text_file(log_path))
        if root is not None:
            return root
    return None


def _default_ksp_save_dir() -> Path | None:
    root = _default_ksp_install_root()
    if root is None:
        return None
    save_name = _default_ksp_save_name()
    if not save_name:
        return None
    return root / "saves" / save_name


def _default_ksp_save_name() -> str | None:
    for log_path in (KSP_PLAYER_LOG, KSP_PLAYER_PREV_LOG):
        if not log_path.exists():
            continue
        save_name = _extract_current_save_name_from_log_text(_read_text_file(log_path))
        if save_name:
            return save_name
    return None


def _active_ksp_save_context() -> dict | None:
    install_root = _default_ksp_install_root()
    save_name = _default_ksp_save_name()
    if install_root is None or not save_name:
        return None
    save_dir = (install_root / "saves" / save_name).resolve()
    save_dir.mkdir(parents=True, exist_ok=True)
    uid_file = save_dir / KSP_SAVE_UID_FILE
    save_uid = _read_text_file(uid_file).strip()
    if not save_uid:
        save_uid = uuid.uuid4().hex
        _write_text_file(uid_file, save_uid)
    return {
        "game_uid": save_uid,
        "save_uid": save_uid,
        "save_name": save_name,
        "save_path": str(save_dir),
        "install_root": str(install_root),
    }


def _color_to_hex(color: QColor | tuple[int, int, int]) -> str:
    if isinstance(color, QColor):
        return color.name()
    return "#{:02x}{:02x}{:02x}".format(*color)


def _make_icon_pixmap(kind: str, size: int = 18, color: QColor | tuple[int, int, int] = QColor("#f0f5fb")) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(_color_to_hex(color)))
    pen.setWidthF(max(1.4, size / 12))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if kind == "edit":
        painter.drawRoundedRect(4, 10, size - 8, 4, 1.5, 1.5)
        painter.drawLine(5, 12, size - 6, 6)
        painter.drawLine(size - 6, 6, size - 4, 8)
        painter.drawLine(size - 8, 4, size - 5, 7)
    elif kind == "globe":
        rect = QRect(3, 3, size - 6, size - 6)
        painter.drawEllipse(rect)
        painter.drawArc(rect.adjusted(3, 4, -3, -4), 0, 360 * 16)
        painter.drawArc(rect.adjusted(0, 6, 0, -6), 90 * 16, 180 * 16)
        painter.drawArc(rect.adjusted(6, 0, -6, 0), 0, 180 * 16)
        painter.drawLine(size // 2, 3, size // 2, size - 4)
    elif kind == "media":
        painter.drawRoundedRect(3, 4, size - 6, size - 8, 3, 3)
        painter.drawLine(6, size - 6, size - 3, size - 6)
        painter.drawLine(5, 8, 10, 11)
        painter.drawLine(10, 11, 7, 14)
        painter.drawLine(5, 8, 13, 8)
    elif kind == "reload":
        painter.drawArc(QRect(3, 3, size - 6, size - 6), 30 * 16, 300 * 16)
        painter.drawLine(size - 6, 5, size - 2, 5)
        painter.drawLine(size - 2, 5, size - 3, 9)
    else:
        painter.drawEllipse(QRect(3, 3, size - 6, size - 6))

    painter.end()
    return pix


class SatelliteStore:
    def __init__(
        self,
        data_file: Path = SATELLITES_FILE,
        groups_file: Path = SATELLITES_GROUPS_FILE,
        games_file: Path = SATELLITES_GAMES_FILE,
    ):
        self.data_file = data_file
        self.groups_file = groups_file
        self.games_file = games_file
        self.records: list[dict] = []
        self.groups: dict[str, dict] = {}
        self.games: dict[str, dict] = {}
        self.current_game_uid = ""
        self.next_id = 1
        self.last_signature = ""
        self.load()

    @staticmethod
    def _timestamp() -> float:
        return time.time()

    @staticmethod
    def _unique_groups(groups: list[str]) -> list[str]:
        result: list[str] = []
        for group in groups:
            key = str(group).strip().upper()
            if key and key not in result:
                result.append(key)
        return result

    def _is_system_group(self, group_name: str) -> bool:
        group = self.groups.get(str(group_name).strip().upper())
        return bool(group and group.get("system"))

    def _filter_manual_groups(self, groups: list[str]) -> list[str]:
        result: list[str] = []
        for group in groups:
            key = str(group).strip().upper()
            if not key or self._is_system_group(key):
                continue
            if key not in result:
                result.append(key)
        return result

    @staticmethod
    def _legacy_game_uid() -> str:
        return "legacy"

    def _satellite_key(self, name: str, launch_ut: float | None, orbit: dict | None = None) -> str:
        launch_part = "unknown" if launch_ut is None else f"{float(launch_ut):.6f}"
        orbit = orbit or {}
        parts = [
            _normalize_key(name),
            launch_part,
            f"{float(orbit.get('periapsis_km', 0) or 0):.1f}",
            f"{float(orbit.get('apoapsis_km', 0) or 0):.1f}",
            f"{float(orbit.get('inclination_deg', 0) or 0):.2f}",
            f"{float(orbit.get('period_s', 0) or 0):.0f}",
            f"{float(orbit.get('eccentricity', 0) or 0):.4f}",
        ]
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    @staticmethod
    def _orbit_similarity_score(left: dict, right: dict) -> float:
        peri_left = float((left.get("orbit") or {}).get("periapsis_km", 0) or 0)
        peri_right = float((right.get("orbit") or {}).get("periapsis_km", 0) or 0)
        apo_left = float((left.get("orbit") or {}).get("apoapsis_km", 0) or 0)
        apo_right = float((right.get("orbit") or {}).get("apoapsis_km", 0) or 0)
        inc_left = float((left.get("orbit") or {}).get("inclination_deg", 0) or 0)
        inc_right = float((right.get("orbit") or {}).get("inclination_deg", 0) or 0)
        period_left = float((left.get("orbit") or {}).get("period_s", 0) or 0)
        period_right = float((right.get("orbit") or {}).get("period_s", 0) or 0)
        ecc_left = float((left.get("orbit") or {}).get("eccentricity", 0) or 0)
        ecc_right = float((right.get("orbit") or {}).get("eccentricity", 0) or 0)
        return (
            abs(peri_left - peri_right) / 2.0 +
            abs(apo_left - apo_right) / 2.0 +
            abs(inc_left - inc_right) * 4.0 +
            abs(period_left - period_right) / 30.0 +
            abs(ecc_left - ecc_right) * 100.0
        )

    def _find_matching_record(self, snapshot: dict, records_by_key: dict[str, dict], current_game_uid: str) -> dict | None:
        key = str(snapshot["identity_key"])
        record = records_by_key.get(key)
        if record is not None:
            return record

        snapshot_name = _normalize_key(snapshot.get("name", ""))
        if not snapshot_name:
            return None

        candidates: list[tuple[float, dict]] = []
        for candidate in self.records:
            if str(candidate.get("game_uid") or current_game_uid) != current_game_uid:
                continue
            if _normalize_key(candidate.get("name", "")) != snapshot_name:
                continue
            if str(candidate.get("status_mode") or "auto") == "manual":
                continue
            score = self._orbit_similarity_score(snapshot, candidate)
            if score <= 6.0:
                candidates.append((score, candidate))

        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], -int(item[1].get("id", 0))))
        return candidates[0][1]

    def _deduplicate_auto_records(self, game_uid: str) -> bool:
        changed = False
        current_records = [record for record in self.records if str(record.get("game_uid") or game_uid) == game_uid]
        kept: list[dict] = []
        removed_ids: set[int] = set()

        for record in current_records:
            if int(record.get("id", 0)) in removed_ids:
                continue
            if str(record.get("status_mode") or "auto") == "manual":
                kept.append(record)
                continue

            merged = False
            for existing in kept:
                if str(existing.get("status_mode") or "auto") == "manual":
                    continue
                if _normalize_key(existing.get("name", "")) != _normalize_key(record.get("name", "")):
                    continue
                if self._orbit_similarity_score(existing, record) > 4.0:
                    continue
                preferred = existing
                if int(record.get("id", 0)) > int(existing.get("id", 0)):
                    preferred = record
                    removed_ids.add(int(existing.get("id", 0)))
                    kept[kept.index(existing)] = record
                else:
                    removed_ids.add(int(record.get("id", 0)))
                if preferred is record:
                    preferred["status"] = preferred.get("status", SATELLITE_STATUS_ACTIVE)
                merged = True
                changed = True
                break
            if not merged:
                kept.append(record)

        if removed_ids:
            self.records = [record for record in self.records if int(record.get("id", 0)) not in removed_ids]
            changed = True
        return changed

    def _groups_for_vessel_type(self, vessel_type_name: str) -> list[str]:
        key = str(vessel_type_name).strip().lower()
        if key == "station":
            return ["ESTACIONES ESPACIALES"]
        if key in {"debris", "dropped_part"}:
            return ["BASURA ESPACIAL"]
        return []

    def _default_game_payload(self, game_uid: str, save_name: str = "", save_path: str = "", install_root: str = "") -> dict:
        return {
            "game_uid": game_uid,
            "save_uid": game_uid,
            "save_name": save_name,
            "save_path": save_path,
            "install_root": install_root,
            "signature": "",
            "first_seen": self._timestamp(),
            "last_seen": self._timestamp(),
            "status": "active",
        }

    def _load_games(self, payload) -> None:
        self.games = {}
        if not isinstance(payload, dict):
            return
        raw_games = payload.get("games", [])
        if isinstance(raw_games, dict):
            raw_games = list(raw_games.values())
        for entry in raw_games:
            if not isinstance(entry, dict):
                continue
            game_uid = str(entry.get("game_uid") or entry.get("save_uid") or "").strip()
            if not game_uid:
                continue
            self.games[game_uid] = {
                "game_uid": game_uid,
                "save_uid": str(entry.get("save_uid") or game_uid),
                "save_name": str(entry.get("save_name") or ""),
                "save_path": str(entry.get("save_path") or ""),
                "install_root": str(entry.get("install_root") or ""),
                "signature": str(entry.get("signature") or ""),
                "first_seen": entry.get("first_seen", self._timestamp()),
                "last_seen": entry.get("last_seen", self._timestamp()),
                "status": str(entry.get("status") or "active"),
            }
        self.current_game_uid = str(payload.get("current_game_uid") or "").strip()

    def load(self) -> None:
        payload = _load_json_file(self.data_file, {})
        self.records = list(payload.get("records", [])) if isinstance(payload, dict) else []
        self.next_id = int(payload.get("next_id", 1)) if isinstance(payload, dict) else 1
        self.last_signature = str(payload.get("last_signature", "")) if isinstance(payload, dict) else ""

        games_payload = _load_json_file(self.games_file, {})
        self._load_games(games_payload)

        groups_payload = _load_json_file(self.groups_file, {})
        self.groups = {}
        if isinstance(groups_payload, dict):
            for key, group in groups_payload.get("groups", {}).items():
                if isinstance(group, dict):
                    self.groups[key] = group
        for key, value in DEFAULT_SATELLITE_GROUPS.items():
            self.groups.setdefault(key, dict(value))

        if not self.games and self.records:
            legacy_uid = self._legacy_game_uid()
            self.games[legacy_uid] = self._default_game_payload(
                legacy_uid,
                save_name="Legado",
                save_path="",
                install_root="",
            )
            self.current_game_uid = legacy_uid

        self._normalize_records()
        if not self.current_game_uid or self.current_game_uid not in self.games:
            if self.games:
                preferred = next((uid for uid in self.games if any(r.get("game_uid") == uid for r in self.records)), None)
                self.current_game_uid = preferred or next(iter(self.games))
            else:
                self.current_game_uid = self._legacy_game_uid()
        if self.current_game_uid not in self.games:
            self.games[self.current_game_uid] = self._default_game_payload(self.current_game_uid, save_name="Legado")
        self.last_signature = str(self.games.get(self.current_game_uid, {}).get("signature", self.last_signature))
        if self._deduplicate_auto_records(self.current_game_uid):
            self.save()

    def save(self) -> None:
        _save_json_file(self.data_file, {
            "next_id": self.next_id,
            "last_signature": self.last_signature,
            "current_game_uid": self.current_game_uid,
            "records": self.records,
        })
        _save_json_file(self.groups_file, {"groups": self.groups})
        _save_json_file(self.games_file, {
            "current_game_uid": self.current_game_uid,
            "games": list(self.games.values()),
        })

    def _normalize_records(self) -> None:
        max_id = 0
        fallback_game_uid = self.current_game_uid or self._legacy_game_uid()
        for record in self.records:
            orbit = record.get("orbit") or {}
            groups_auto = list(record.get("groups_auto") or [])
            groups_manual = list(record.get("groups_manual") or [])
            legacy_group = str(record.get("group", "") or "").strip().upper()

            record.setdefault("id", 0)
            record.setdefault("game_uid", fallback_game_uid)
            record.setdefault("ksp_identity_key", "")
            record.setdefault("name", "")
            record.setdefault("description", "")
            record.setdefault("status", SATELLITE_STATUS_ACTIVE)
            record.setdefault("status_mode", "auto")
            record.setdefault("multimedia", [])
            record.setdefault("launch_ut", None)
            record.setdefault("launch_date", _format_ksp_ut(record.get("launch_ut")))

            if not groups_auto:
                groups_auto = [_auto_group_for_altitude(float(orbit.get("apoapsis_km", 0) or 0))]
            if not groups_manual and legacy_group and legacy_group not in DEFAULT_SATELLITE_GROUPS:
                groups_manual = [legacy_group]
            elif not groups_manual and legacy_group and legacy_group in DEFAULT_SATELLITE_GROUPS and not record.get("group_manual", False):
                groups_auto = [legacy_group]

            record["groups_auto"] = self._unique_groups(groups_auto)
            record["groups_manual"] = self._filter_manual_groups(groups_manual)
            record["groups"] = self._unique_groups(record["groups_auto"] + record["groups_manual"])
            record["group"] = record["groups"][0] if record["groups"] else ""
            record["group_manual"] = bool(record["groups_manual"])
            if not record.get("ksp_identity_key"):
                record["ksp_identity_key"] = self._satellite_key(record.get("name", ""), record.get("launch_ut"), orbit)
            max_id = max(max_id, int(record["id"]))

        if self.next_id <= max_id:
            self.next_id = max_id + 1

    def _sync_group_fields(self, record: dict) -> None:
        record["groups_auto"] = self._unique_groups(list(record.get("groups_auto") or []))
        record["groups_manual"] = self._unique_groups(list(record.get("groups_manual") or []))
        record["groups"] = self._unique_groups(record["groups_auto"] + record["groups_manual"])
        record["group"] = record["groups"][0] if record["groups"] else ""
        record["group_manual"] = bool(record["groups_manual"])

    def _allocate_id(self) -> int:
        satellite_id = self.next_id
        self.next_id += 1
        return satellite_id

    def _media_base_dir(self, satellite_id: int) -> Path:
        return SATELLITES_MEDIA_DIR / f"sat_{int(satellite_id)}"

    def resolve_media_path(self, satellite_id: int, stored_path: str) -> Path:
        path = Path(stored_path)
        if path.is_absolute():
            return path
        return (BASE_DIR / path).resolve()

    def import_media_files(self, satellite_id: int, selected_files: list[str]) -> list[dict]:
        target_dir = self._media_base_dir(satellite_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        imported: list[dict] = []
        for source_name in selected_files:
            source = Path(source_name)
            if not source.exists():
                continue
            stem = source.stem
            suffix = source.suffix.lower()
            destination = target_dir / source.name
            counter = 1
            while destination.exists():
                destination = target_dir / f"{stem}_{counter}{suffix}"
                counter += 1
            shutil.copy2(source, destination)
            imported.append({
                "path": str(destination.relative_to(BASE_DIR)),
                "label": source.stem,
            })
        return imported

    def normalize_multimedia_entries(self, satellite_id: int, entries: list[dict]) -> list[dict]:
        target_dir = self._media_base_dir(satellite_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        normalized: list[dict] = []
        for entry in entries:
            raw_path = str(entry.get("path", "")).strip()
            label = str(entry.get("label") or Path(raw_path).stem or "Multimedia").strip()
            if not raw_path:
                continue
            path_obj = Path(raw_path)
            if path_obj.is_absolute() and not str(path_obj).startswith(str(SATELLITES_MEDIA_DIR)):
                if path_obj.exists():
                    imported = self.import_media_files(satellite_id, [str(path_obj)])
                    if imported:
                        imported[0]["label"] = label
                        normalized.append(imported[0])
                    continue
            if path_obj.is_absolute():
                try:
                    rel = str(path_obj.relative_to(BASE_DIR))
                except ValueError:
                    rel = str(path_obj)
                normalized.append({"path": rel, "label": label})
            else:
                normalized.append({"path": raw_path, "label": label})
        return normalized

    def _get_group(self, group_name: str) -> dict | None:
        return self.groups.get(group_name)

    def _launch_ut_for_vessel(self, vessel) -> float | None:
        for attr in ("launch_time", "launch_time_ut", "launch_ut"):
            try:
                value = getattr(vessel, attr)
            except Exception:
                value = None
            if isinstance(value, (int, float)):
                return float(value)
        return None

    def _snapshot_from_connection(self, conn) -> list[dict]:
        snapshots: list[dict] = []
        vessels = []
        try:
            vessels = list(conn.space_center.vessels)
        except Exception:
            return snapshots
        for vessel in vessels:
            try:
                orbit = vessel.orbit
                situation_name = getattr(getattr(vessel, "situation", None), "name", "")
                if situation_name not in {"orbiting", "escaping"}:
                    continue
                periapsis_km = max(0.0, float(getattr(orbit, "periapsis_altitude", 0.0) or 0.0) / 1000.0)
                apoapsis_km = max(0.0, float(getattr(orbit, "apoapsis_altitude", 0.0) or 0.0) / 1000.0)
                launch_ut = self._launch_ut_for_vessel(vessel)
                name = str(getattr(vessel, "name", "")).strip()
                vessel_type_obj = getattr(vessel, "type", None)
                vessel_type_name = str(getattr(vessel_type_obj, "name", vessel_type_obj) or "").strip().lower()
                orbit_payload = {
                    "periapsis_km": round(periapsis_km, 3),
                    "apoapsis_km": round(apoapsis_km, 3),
                    "inclination_deg": round(math.degrees(float(getattr(orbit, "inclination", 0.0) or 0.0)), 6),
                    "period_s": round(float(getattr(orbit, "period", 0.0) or 0.0), 3),
                    "eccentricity": round(float(getattr(orbit, "eccentricity", 0.0) or 0.0), 6),
                }
                snapshots.append({
                    "name": name,
                    "periapsis_km": orbit_payload["periapsis_km"],
                    "apoapsis_km": orbit_payload["apoapsis_km"],
                    "inclination_deg": orbit_payload["inclination_deg"],
                    "period_s": orbit_payload["period_s"],
                    "eccentricity": orbit_payload["eccentricity"],
                    "launch_ut": launch_ut,
                    "vessel_type": vessel_type_name,
                    "identity_key": self._satellite_key(name, launch_ut, orbit_payload),
                })
            except Exception:
                continue
        snapshots.sort(key=lambda item: (item["name"].lower(), item["identity_key"]))
        return snapshots

    def snapshot_signature(self, conn) -> str:
        payload = self._snapshot_from_connection(conn)
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _default_game_context(self) -> dict:
        uid = self.current_game_uid or self._legacy_game_uid()
        game = self.games.get(uid)
        if game is None:
            game = self._default_game_payload(uid, save_name="Legado")
            self.games[uid] = game
        self.current_game_uid = uid
        return game

    def _read_or_create_save_uid(self, save_dir: Path) -> str:
        uid_file = save_dir / KSP_SAVE_UID_FILE
        existing = _read_text_file(uid_file).strip()
        if existing:
            return existing
        new_uid = uuid.uuid4().hex
        _write_text_file(uid_file, new_uid)
        return new_uid

    def _detect_current_game_context(self) -> dict | None:
        install_root = _default_ksp_install_root()
        save_name = _default_ksp_save_name()
        if install_root is None or not save_name:
            return None
        save_dir = (install_root / "saves" / save_name).resolve()
        save_dir.mkdir(parents=True, exist_ok=True)
        save_uid = self._read_or_create_save_uid(save_dir)
        return {
            "game_uid": save_uid,
            "save_uid": save_uid,
            "save_name": save_name,
            "save_path": str(save_dir),
            "install_root": str(install_root),
        }

    def _register_game_context(self, context: dict) -> dict:
        game_uid = str(context["game_uid"]).strip()
        save_dir = Path(str(context["save_path"]))
        save_name = str(context.get("save_name") or "").strip()
        install_root = str(context.get("install_root") or "").strip()

        existing = self.games.get(game_uid)
        if existing is not None:
            existing_path_str = str(existing.get("save_path") or "").strip()
            existing_path = Path(existing_path_str) if existing_path_str else None
            if existing_path is not None and existing_path.resolve() != save_dir.resolve():
                if existing_path.exists():
                    game_uid = uuid.uuid4().hex
                    _write_text_file(save_dir / KSP_SAVE_UID_FILE, game_uid)
                    existing = None
                else:
                    existing["save_path"] = str(save_dir)
                    existing["save_name"] = save_name or existing.get("save_name", "")
                    existing["install_root"] = install_root or existing.get("install_root", "")
                    existing["last_seen"] = self._timestamp()
                    self.current_game_uid = game_uid
                    self.last_signature = str(existing.get("signature", self.last_signature))
                    return existing
            else:
                existing["save_path"] = str(save_dir)
                existing["save_name"] = save_name or existing.get("save_name", "")
                existing["install_root"] = install_root or existing.get("install_root", "")
                existing["last_seen"] = self._timestamp()
                self.current_game_uid = game_uid
                self.last_signature = str(existing.get("signature", self.last_signature))
                return existing

        game = self._default_game_payload(game_uid, save_name=save_name, save_path=str(save_dir), install_root=install_root)
        self.games[game_uid] = game
        self.current_game_uid = game_uid
        self.last_signature = str(game.get("signature", self.last_signature))
        return game

    def _migrate_legacy_records_to(self, game_uid: str) -> bool:
        legacy_records = [record for record in self.records if record.get("game_uid") in {"", self._legacy_game_uid()}]
        if not legacy_records:
            return False
        if any(record.get("game_uid") == game_uid for record in self.records):
            return False
        for record in legacy_records:
            record["game_uid"] = game_uid
        self.games.pop(self._legacy_game_uid(), None)
        return True

    def sync_from_connection(self, conn) -> bool:
        context = self._detect_current_game_context()
        if context is None:
            game = self._default_game_context()
        else:
            game = self._register_game_context(context)

        current_game_uid = str(game.get("game_uid") or self.current_game_uid or self._legacy_game_uid())
        changed = False
        if self._migrate_legacy_records_to(current_game_uid):
            changed = True

        current_snapshot = self._snapshot_from_connection(conn)
        current_signature = hashlib.sha256(json.dumps(current_snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        current_keys = set()
        records_by_key = {
            str(record.get("ksp_identity_key") or self._satellite_key(record.get("name", ""), record.get("launch_ut"), record.get("orbit") or {})): record
            for record in self.records
            if str(record.get("game_uid") or current_game_uid) == current_game_uid
        }

        for sat in current_snapshot:
            key = str(sat["identity_key"])
            current_keys.add(key)
            altitude_for_group = max(0.0, (sat["periapsis_km"] + sat["apoapsis_km"]) / 2.0)
            default_groups = self._unique_groups([
                _auto_group_for_altitude(altitude_for_group),
                *self._groups_for_vessel_type(sat.get("vessel_type", "")),
            ])
            launch_ut = sat.get("launch_ut")
            if launch_ut is None:
                try:
                    launch_ut = float(conn.space_center.ut)
                except Exception:
                    launch_ut = None

            record = self._find_matching_record(sat, records_by_key, current_game_uid)
            if record is None:
                record = {
                    "id": self._allocate_id(),
                    "game_uid": current_game_uid,
                    "ksp_identity_key": key,
                    "name": sat["name"],
                    "description": "",
                    "groups_auto": default_groups,
                    "groups_manual": [],
                    "groups": default_groups,
                    "group": default_groups[0] if default_groups else "",
                    "group_manual": False,
                    "orbit": {},
                    "launch_ut": launch_ut,
                    "launch_date": _format_ksp_ut(launch_ut),
                    "status": SATELLITE_STATUS_ACTIVE,
                    "status_mode": "auto",
                    "multimedia": [],
                }
                self.records.append(record)
                records_by_key[key] = record
                changed = True
            else:
                previous_key = str(record.get("ksp_identity_key") or "")
                if record.get("game_uid") != current_game_uid:
                    record["game_uid"] = current_game_uid
                    changed = True
                if record.get("name") != sat["name"]:
                    record["name"] = sat["name"]
                    changed = True
                if not record.get("launch_ut") and launch_ut is not None:
                    record["launch_ut"] = launch_ut
                    record["launch_date"] = _format_ksp_ut(launch_ut)
                    changed = True

            orbit_payload = {
                "periapsis_km": sat["periapsis_km"],
                "apoapsis_km": sat["apoapsis_km"],
                "inclination_deg": sat["inclination_deg"],
                "period_s": sat["period_s"],
                "eccentricity": sat["eccentricity"],
            }
            if record.get("orbit") != orbit_payload:
                record["orbit"] = orbit_payload
                changed = True
                if record.get("groups_auto") != default_groups:
                    record["groups_auto"] = default_groups
                    changed = True
                record["ksp_identity_key"] = key
                if previous_key and previous_key != key:
                    records_by_key.pop(previous_key, None)
                records_by_key[key] = record
                self._sync_group_fields(record)
                if record.get("status_mode") == "auto" and record.get("status") == SATELLITE_STATUS_OFFLINE:
                    record["status"] = SATELLITE_STATUS_ACTIVE
                    changed = True
            elif not record.get("status"):
                record["status"] = SATELLITE_STATUS_ACTIVE
                record["status_mode"] = "auto"
                changed = True

        for record in self.records:
            if str(record.get("game_uid") or current_game_uid) != current_game_uid:
                continue
            if str(record.get("ksp_identity_key") or "") not in current_keys and record.get("status") != SATELLITE_STATUS_OFFLINE:
                record["status"] = SATELLITE_STATUS_OFFLINE
                record["status_mode"] = "auto"
                changed = True

        game["signature"] = current_signature
        game["last_seen"] = self._timestamp()
        self.current_game_uid = current_game_uid
        self.last_signature = current_signature
        if self._deduplicate_auto_records(current_game_uid):
            changed = True
        self._normalize_records()
        self.save()
        return changed

    def visible_records(self) -> list[dict]:
        if not self.current_game_uid:
            return list(self.records)
        return [record for record in self.records if str(record.get("game_uid") or self.current_game_uid) == self.current_game_uid]

    def get_record_by_id(self, satellite_id: int) -> dict | None:
        for record in self.records:
            if int(record.get("id", 0)) == int(satellite_id):
                return record
        return None

    def update_satellite(
        self,
        satellite_id: int,
        *,
        description: str | None = None,
        groups_manual: list[str] | None = None,
        multimedia: list[dict] | None = None,
        status: str | None = None,
    ) -> None:
        record = self.get_record_by_id(satellite_id)
        if record is None:
            return
        if description is not None:
            record["description"] = description.strip()
        if groups_manual is not None:
            record["groups_manual"] = self._filter_manual_groups(groups_manual)
            self._sync_group_fields(record)
        if multimedia is not None:
            record["multimedia"] = multimedia
        if status is not None:
            record["status"] = status
            record["status_mode"] = "manual"
        self.save()

    def update_satellite_groups(self, satellite_id: int, groups_manual: list[str]) -> None:
        record = self.get_record_by_id(satellite_id)
        if record is None:
            return
        record["groups_manual"] = self._filter_manual_groups(groups_manual)
        self._sync_group_fields(record)
        self.save()

    def update_satellite_media(self, satellite_id: int, media_files: list[str]) -> list[dict]:
        record = self.get_record_by_id(satellite_id)
        if record is None:
            return []
        imported = self.import_media_files(satellite_id, media_files)
        record["multimedia"] = list(record.get("multimedia", [])) + imported
        self.save()
        return imported

    def create_group(self, name: str, full_name: str, description: str) -> bool:
        key = name.strip().upper()
        if not key or key in self.groups:
            return False
        self.groups[key] = {
            "name": key,
            "full_name": full_name.strip() or key,
            "description": description.strip(),
            "min_alt_km": None,
            "max_alt_km": None,
            "system": False,
        }
        self.save()
        return True

    def update_group(self, name: str, full_name: str, description: str) -> bool:
        group = self.groups.get(name)
        if not group or group.get("system"):
            return False
        group["full_name"] = full_name.strip() or name
        group["description"] = description.strip()
        self.save()
        return True

    def rename_group(self, old_name: str, new_name: str, full_name: str, description: str) -> bool:
        group = self.groups.get(old_name)
        new_key = new_name.strip().upper()
        if not group or group.get("system") or not new_key or (new_key != old_name and new_key in self.groups):
            return False
        if new_key != old_name:
            self.groups[new_key] = self.groups.pop(old_name)
            for record in self.records:
                if old_name in (record.get("groups") or []):
                    record["groups_manual"] = [new_key if group_name == old_name else group_name for group_name in (record.get("groups_manual") or [])]
                    record["groups_auto"] = [new_key if group_name == old_name else group_name for group_name in (record.get("groups_auto") or [])]
                    self._sync_group_fields(record)
        group = self.groups[new_key]
        group["name"] = new_key
        group["full_name"] = full_name.strip() or new_key
        group["description"] = description.strip()
        self.save()
        return True

    def delete_group(self, name: str) -> bool:
        group = self.groups.get(name)
        if not group or group.get("system"):
            return False
        del self.groups[name]
        for record in self.records:
            if name in (record.get("groups_manual") or []):
                record["groups_manual"] = [group_name for group_name in (record.get("groups_manual") or []) if group_name != name]
                self._sync_group_fields(record)
        self.save()
        return True


class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ElidedClickableLabel(ClickableLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._full_text = text
        self.setToolTip(text)
        self._update_text()

    def set_full_text(self, text: str) -> None:
        self._full_text = text
        self._update_text()
        self.setToolTip(text)

    def resizeEvent(self, event) -> None:
        self._update_text()
        super().resizeEvent(event)

    def _update_text(self) -> None:
        available = max(40, self.width() - 12)
        self.setText(_elide_text(self._full_text, available, self.font()))


class IconToolButton(QToolButton):
    def __init__(self, icon_kind: str, tooltip: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setIconSize(QSize(18, 18))
        self.setAutoRaise(True)
        self.setIcon(QIcon(_make_icon_pixmap(icon_kind)))
        self.setObjectName("iconToolButton")


class GlassDialog(QDialog):
    def __init__(self, title: str, width: int = 760, height: int = 560, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.resize(width, height)
        self.setStyleSheet("QDialog { background: #07111d; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)

        self.panel = GlassPanel()
        self.panel.setObjectName("modalPanel")
        self.panel.setStyleSheet("""
            QFrame#modalPanel {
                background: #101d2c;
                border: 1px solid rgba(126, 164, 196, 90);
                border-radius: 14px;
            }
        """)
        outer.addWidget(self.panel)

        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(18, 16, 18, 18)
        panel_layout.setSpacing(14)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("title")
        header.addWidget(self.title_label)
        header.addStretch()

        self.close_button = QPushButton("Cerrar")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(self.reject)
        header.addWidget(self.close_button)
        panel_layout.addLayout(header)

        self.body_layout = QVBoxLayout()
        self.body_layout.setSpacing(12)
        panel_layout.addLayout(self.body_layout)

        fade_in(self.panel, 180)


class SatelliteDescriptionDialog(GlassDialog):
    def __init__(self, satellite: dict, parent: QWidget | None = None):
        super().__init__("Descripción del satélite", 760, 580, parent)
        self.satellite = satellite

        name = QLabel(satellite.get("name", ""))
        name.setObjectName("transitionTitle")
        self.body_layout.addWidget(name)

        meta = QLabel(f"ID {satellite.get('id', '—')} · Grupo {satellite.get('group', '—')} · Estado {satellite.get('status', '—')}")
        meta.setObjectName("muted")
        self.body_layout.addWidget(meta)

        self.editor = QTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setPlainText(satellite.get("description", "") or "Sin descripción disponible.")
        self.editor.setMinimumHeight(380)
        self.body_layout.addWidget(self.editor)

        footer = QHBoxLayout()
        footer.addStretch()
        close_btn = QPushButton("Volver")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        self.body_layout.addLayout(footer)


class SatelliteMediaDialog(GlassDialog):
    def __init__(self, satellite: dict, parent: QWidget | None = None):
        super().__init__("Multimedia del satélite", 920, 650, parent)
        self.satellite = satellite
        self.entries = list(satellite.get("multimedia", []) or [])
        self.index = 0
        self._player = None
        self._audio = None

        title = QLabel(satellite.get("name", ""))
        title.setObjectName("transitionTitle")
        self.body_layout.addWidget(title)

        self.viewer_stack = QStackedWidget()
        self.viewer_stack.setMinimumHeight(420)
        self.viewer_stack.setStyleSheet("background: #08131d; border-radius: 12px;")
        self.body_layout.addWidget(self.viewer_stack)

        self.image_view = QLabel("Sin contenido multimedia")
        self.image_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_view.setStyleSheet("color:#91a8bb; padding: 24px;")
        self.image_view.setScaledContents(False)
        self.viewer_stack.addWidget(self.image_view)

        if _MULTIMEDIA_AVAILABLE:
            self.video_view = QVideoWidget()
            self.viewer_stack.addWidget(self.video_view)
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
            self._player.setVideoOutput(self.video_view)

        nav = QHBoxLayout()
        self.prev_btn = QPushButton("Anterior")
        self.prev_btn.clicked.connect(self._previous)
        self.next_btn = QPushButton("Siguiente")
        self.next_btn.clicked.connect(self._next)
        self.counter_label = QLabel("")
        self.counter_label.setObjectName("muted")
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.next_btn)
        nav.addStretch()
        nav.addWidget(self.counter_label)
        self.body_layout.addLayout(nav)

        footer = QHBoxLayout()
        footer.addStretch()
        close_btn = QPushButton("Volver")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        self.body_layout.addLayout(footer)

        self._show_current()

    def reject(self) -> None:
        if self._player is not None:
            self._player.stop()
        super().reject()

    def _current_entry(self) -> dict | None:
        if not self.entries:
            return None
        self.index %= len(self.entries)
        return self.entries[self.index]

    def _is_video(self, path: str) -> bool:
        return Path(path).suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".avi"}

    def _show_current(self) -> None:
        entry = self._current_entry()
        if entry is None:
            self.counter_label.setText("0/0")
            self.image_view.setText("Sin contenido multimedia")
            self.viewer_stack.setCurrentWidget(self.image_view)
            return

        path = str(entry.get("path", "")).strip()
        label = str(entry.get("label") or Path(path).name or "Elemento multimedia")
        self.counter_label.setText(f"{self.index + 1}/{len(self.entries)} · {label}")

        if self._player is not None:
            self._player.stop()

        path_obj = Path(path)
        resolved_path = path_obj if path_obj.is_absolute() else (BASE_DIR / path_obj)
        if path and resolved_path.exists() and self._is_video(path) and _MULTIMEDIA_AVAILABLE:
            self.viewer_stack.setCurrentWidget(self.video_view)
            self._player.setSource(QUrl.fromLocalFile(str(resolved_path.resolve())))
            self._player.play()
            return

        pix = QPixmap(str(resolved_path)) if path else QPixmap()
        if pix.isNull():
            self.image_view.setText("No se pudo cargar el archivo multimedia.")
            self.viewer_stack.setCurrentWidget(self.image_view)
            return
        scaled = pix.scaled(
            self.viewer_stack.size().expandedTo(QSize(800, 420)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_view.setPixmap(scaled)
        self.viewer_stack.setCurrentWidget(self.image_view)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        current = self._current_entry()
        if current is not None and self.viewer_stack.currentWidget() == self.image_view and self.image_view.pixmap() is not None:
            self._show_current()

    def _previous(self) -> None:
        if not self.entries:
            return
        self.index = (self.index - 1) % len(self.entries)
        self._show_current()

    def _next(self) -> None:
        if not self.entries:
            return
        self.index = (self.index + 1) % len(self.entries)
        self._show_current()


class SatelliteEditDialog(GlassDialog):
    def __init__(self, store: SatelliteStore, satellite: dict, available_groups: list[str], parent: QWidget | None = None):
        super().__init__("Editar satélite", 860, 700, parent)
        self.store = store
        self.satellite = satellite
        self.available_groups = available_groups
        self.selected_groups = list(satellite.get("groups") or [])

        title = QLabel(satellite.get("name", ""))
        title.setObjectName("transitionTitle")
        self.body_layout.addWidget(title)

        self.body_layout.addWidget(QLabel(f"ID {satellite.get('id', '—')}"))

        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("Descripción adicional")
        self.description_edit.setPlainText(satellite.get("description", "") or "")
        self.body_layout.addWidget(QLabel("Descripción"))
        self.body_layout.addWidget(self.description_edit)

        self.status_combo = QComboBox()
        self.status_combo.addItems([SATELLITE_STATUS_ACTIVE, SATELLITE_STATUS_MAINTENANCE, SATELLITE_STATUS_OFFLINE])
        self.status_combo.setCurrentText(satellite.get("status", SATELLITE_STATUS_ACTIVE))

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.addWidget(QLabel("Grupo"), 0, 0)
        group_row = QHBoxLayout()
        self.group_summary = QLabel(self._group_summary())
        self.group_summary.setWordWrap(True)
        self.group_summary.setObjectName("muted")
        self.group_button = QPushButton("Seleccionar grupos")
        self.group_button.clicked.connect(self._select_groups)
        group_row.addWidget(self.group_summary, 1)
        group_row.addWidget(self.group_button)
        grid.addLayout(group_row, 0, 1)
        grid.addWidget(QLabel("Estado"), 0, 2)
        grid.addWidget(self.status_combo, 0, 3)
        self.body_layout.addLayout(grid)

        self.media_list = QListWidget()
        self.media_list.setMinimumHeight(160)
        self.body_layout.addWidget(QLabel("Multimedia"))
        self.body_layout.addWidget(self.media_list)
        self._load_media_items()

        media_buttons = QHBoxLayout()
        add_media_btn = QPushButton("Añadir")
        add_media_btn.clicked.connect(self._add_media)
        remove_media_btn = QPushButton("Eliminar")
        remove_media_btn.clicked.connect(self._remove_selected_media)
        media_buttons.addWidget(add_media_btn)
        media_buttons.addWidget(remove_media_btn)
        media_buttons.addStretch()
        self.body_layout.addLayout(media_buttons)

        footer = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        footer.accepted.connect(self.accept)
        footer.rejected.connect(self.reject)
        self.body_layout.addWidget(footer)

    def _group_summary(self) -> str:
        if not self.selected_groups:
            return "Sin grupos asignados"
        return ", ".join(self.selected_groups)

    def _select_groups(self) -> None:
        dialog = SatelliteGroupSelectionDialog(
            self.store,
            self.selected_groups,
            locked_groups=list(self.satellite.get("groups_auto") or []),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.selected_groups = dialog.selected_groups()
        self.group_summary.setText(self._group_summary())

    def _load_media_items(self) -> None:
        self.media_list.clear()
        for item in self.satellite.get("multimedia", []) or []:
            path = str(item.get("path", ""))
            label = str(item.get("label") or Path(path).name)
            item_widget = QListWidgetItem(f"{label} · {Path(path).suffix.upper().lstrip('.') or 'ARCHIVO'}")
            item_widget.setData(Qt.ItemDataRole.UserRole, dict(item))
            self.media_list.addItem(item_widget)

    def _add_media(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Añadir multimedia",
            str(BASE_DIR),
            "Media (*.png *.jpg *.jpeg *.bmp *.gif *.mp4 *.mov *.mkv *.webm *.avi);;Todos los archivos (*)",
        )
        for file_name in files:
            if not file_name:
                continue
            data = {"path": str(Path(file_name).resolve()), "label": Path(file_name).stem}
            item = QListWidgetItem(f"{data['label']} · {Path(file_name).suffix.upper().lstrip('.')}")
            item.setData(Qt.ItemDataRole.UserRole, data)
            self.media_list.addItem(item)

    def _remove_selected_media(self) -> None:
        row = self.media_list.currentRow()
        if row >= 0:
            self.media_list.takeItem(row)

    def result_payload(self) -> dict:
        multimedia = []
        for index in range(self.media_list.count()):
            item = self.media_list.item(index)
            payload = item.data(Qt.ItemDataRole.UserRole) or {}
            multimedia.append({
                "path": payload.get("path", ""),
                "label": payload.get("label", ""),
            })
        return {
            "description": self.description_edit.toPlainText().strip(),
            "selected_groups": list(self.selected_groups),
            "status": self.status_combo.currentText().strip(),
            "multimedia": multimedia,
        }


class SatelliteFilterDialog(GlassDialog):
    def __init__(self, groups: list[str], selected_groups: set[str], selected_states: set[str], parent: QWidget | None = None):
        super().__init__("Filtros", 560, 520, parent)
        self.group_checks: dict[str, QCheckBox] = {}
        self.state_checks: dict[str, QCheckBox] = {}

        self.body_layout.addWidget(QLabel("Filtrar por grupo"))
        group_box = QFrame()
        group_layout = QVBoxLayout(group_box)
        for group in groups:
            cb = QCheckBox(group)
            cb.setChecked(group in selected_groups)
            self.group_checks[group] = cb
            group_layout.addWidget(cb)
        self.body_layout.addWidget(group_box)

        self.body_layout.addWidget(QLabel("Filtrar por estado"))
        state_box = QFrame()
        state_layout = QVBoxLayout(state_box)
        for state in [SATELLITE_STATUS_ACTIVE, SATELLITE_STATUS_MAINTENANCE, SATELLITE_STATUS_OFFLINE]:
            cb = QCheckBox(state)
            cb.setChecked(state in selected_states)
            self.state_checks[state] = cb
            state_layout.addWidget(cb)
        self.body_layout.addWidget(state_box)

        buttons = QHBoxLayout()
        clear_btn = QPushButton("Borrar filtros")
        clear_btn.clicked.connect(self._clear)
        apply_btn = QPushButton("Aplicar")
        apply_btn.clicked.connect(self.accept)
        buttons.addWidget(clear_btn)
        buttons.addStretch()
        buttons.addWidget(apply_btn)
        self.body_layout.addLayout(buttons)

    def _clear(self) -> None:
        for cb in self.group_checks.values():
            cb.setChecked(False)
        for cb in self.state_checks.values():
            cb.setChecked(False)

    def selected_groups(self) -> set[str]:
        return {group for group, cb in self.group_checks.items() if cb.isChecked()}

    def selected_states(self) -> set[str]:
        return {state for state, cb in self.state_checks.items() if cb.isChecked()}


class SatelliteSortDialog(GlassDialog):
    def __init__(self, sort_key: str, sort_descending: bool, parent: QWidget | None = None):
        super().__init__("Ordenar", 500, 300, parent)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Nombre", "Fecha de lanzamiento"])
        self.sort_combo.setCurrentText("Fecha de lanzamiento" if sort_key == "launch" else "Nombre")

        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["Ascendente", "Descendente"])
        self.direction_combo.setCurrentText("Descendente" if sort_descending else "Ascendente")

        grid = QGridLayout()
        grid.addWidget(QLabel("Ordenar por"), 0, 0)
        grid.addWidget(self.sort_combo, 0, 1)
        grid.addWidget(QLabel("Dirección"), 1, 0)
        grid.addWidget(self.direction_combo, 1, 1)
        self.body_layout.addLayout(grid)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.body_layout.addWidget(buttons)

    def result_payload(self) -> tuple[str, bool]:
        return (
            "launch" if self.sort_combo.currentText() == "Fecha de lanzamiento" else "name",
            self.direction_combo.currentText() == "Descendente",
        )


class GroupFormDialog(GlassDialog):
    def __init__(self, title: str, name: str = "", full_name: str = "", description: str = "", parent: QWidget | None = None):
        super().__init__(title, 580, 360, parent)
        self.name_edit = QLineEdit(name)
        self.full_name_edit = QLineEdit(full_name)
        self.description_edit = QTextEdit(description)
        self.description_edit.setMinimumHeight(120)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.addWidget(QLabel("Nombre"), 0, 0)
        form.addWidget(self.name_edit, 0, 1)
        form.addWidget(QLabel("Nombre completo"), 1, 0)
        form.addWidget(self.full_name_edit, 1, 1)
        form.addWidget(QLabel("Descripción"), 2, 0)
        form.addWidget(self.description_edit, 2, 1)
        self.body_layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.body_layout.addWidget(buttons)

    def result_payload(self) -> tuple[str, str, str]:
        return (
            self.name_edit.text().strip(),
            self.full_name_edit.text().strip(),
            self.description_edit.toPlainText().strip(),
        )


class SatelliteGroupSelectionDialog(GlassDialog):
    def __init__(self, store: SatelliteStore, selected_groups: list[str], locked_groups: list[str] | None = None, parent: QWidget | None = None):
        super().__init__("Grupos del satélite", 560, 580, parent)
        self.store = store
        self.group_checks: dict[str, QCheckBox] = {}
        self.locked_groups = {group.upper() for group in (locked_groups or [])}
        self.selected_groups_initial = {group.upper() for group in selected_groups} | self.locked_groups

        info = QLabel("Selecciona uno o varios grupos para este satélite.")
        info.setObjectName("muted")
        self.body_layout.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        for key, group in self.store.groups.items():
            is_system = bool(group.get("system"))
            locked = key in self.locked_groups or is_system
            label = f"{key} · {group.get('full_name', key)}" + (" · Automático" if locked else "")
            checkbox = QCheckBox(label)
            checkbox.setChecked(key in self.selected_groups_initial if not is_system else key in self.locked_groups)
            checkbox.setEnabled(not is_system)
            self.group_checks[key] = checkbox
            layout.addWidget(checkbox)
        layout.addStretch()
        scroll.setWidget(container)
        self.body_layout.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        clear_btn = QPushButton("Limpiar")
        clear_btn.clicked.connect(self._clear)
        buttons.addWidget(clear_btn)
        buttons.addStretch()
        ok_btn = QPushButton("Guardar")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(ok_btn)
        self.body_layout.addLayout(buttons)

    def _clear(self) -> None:
        for checkbox in self.group_checks.values():
            if checkbox.isEnabled():
                checkbox.setChecked(False)
        for key in self.locked_groups:
            checkbox = self.group_checks.get(key)
            if checkbox is not None:
                checkbox.setChecked(True)

    def selected_groups(self) -> list[str]:
        groups = [key for key, checkbox in self.group_checks.items() if checkbox.isChecked() and checkbox.isEnabled()]
        for key in self.locked_groups:
            if key not in groups and key in self.group_checks:
                groups.append(key)
        return groups


class SatelliteGroupsDialog(GlassDialog):
    def __init__(self, store: SatelliteStore, on_changed, parent: QWidget | None = None):
        super().__init__("Grupos", 860, 620, parent)
        self.store = store
        self.on_changed = on_changed

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Grupo", "Nombre completo", "Descripción", "Estado"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.body_layout.addWidget(self.table)

        buttons = QHBoxLayout()
        self.add_btn = QPushButton("Crear grupo")
        self.add_btn.clicked.connect(self._create_group)
        self.edit_btn = QPushButton("Editar grupo")
        self.edit_btn.clicked.connect(self._edit_group)
        self.delete_btn = QPushButton("Eliminar grupo")
        self.delete_btn.clicked.connect(self._delete_group)
        close_btn = QPushButton("Volver")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(self.add_btn)
        buttons.addWidget(self.edit_btn)
        buttons.addWidget(self.delete_btn)
        buttons.addStretch()
        buttons.addWidget(close_btn)
        self.body_layout.addLayout(buttons)

        self._reload_table()

    def _reload_table(self) -> None:
        groups = list(self.store.groups.values())
        self.table.setRowCount(len(groups))
        for row, group in enumerate(groups):
            name_item = QTableWidgetItem(group.get("name", ""))
            full_item = QTableWidgetItem(group.get("full_name", ""))
            desc_item = QTableWidgetItem(group.get("description", ""))
            state_item = QTableWidgetItem("Sistema" if group.get("system") else "Usuario")
            for col, item in enumerate([name_item, full_item, desc_item, state_item]):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, col, item)

    def _selected_group_name(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None

    def _create_group(self) -> None:
        dialog = GroupFormDialog("Crear grupo", parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, full_name, description = dialog.result_payload()
        if not name:
            QMessageBox.warning(self, APP_NAME, "El grupo necesita un nombre.")
            return
        if not self.store.create_group(name, full_name, description):
            QMessageBox.warning(self, APP_NAME, "No se pudo crear el grupo.")
            return
        self._reload_table()
        self.on_changed()

    def _edit_group(self) -> None:
        name = self._selected_group_name()
        if not name:
            return
        group = self.store.groups.get(name)
        if not group or group.get("system"):
            QMessageBox.information(self, APP_NAME, "Los grupos predeterminados no se pueden modificar.")
            return
        dialog = GroupFormDialog("Editar grupo", name=group.get("name", ""), full_name=group.get("full_name", ""), description=group.get("description", ""), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_name, full_name, description = dialog.result_payload()
        if not new_name:
            QMessageBox.warning(self, APP_NAME, "El grupo necesita un nombre.")
            return
        if new_name.upper() != name.upper():
            ok = self.store.rename_group(name, new_name, full_name, description)
        else:
            ok = self.store.update_group(name, full_name, description)
        if not ok:
            QMessageBox.warning(self, APP_NAME, "No se pudo actualizar el grupo.")
            return
        self._reload_table()
        self.on_changed()

    def _delete_group(self) -> None:
        name = self._selected_group_name()
        if not name:
            return
        group = self.store.groups.get(name)
        if not group or group.get("system"):
            QMessageBox.information(self, APP_NAME, "Los grupos predeterminados no se pueden eliminar.")
            return
        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"¿Eliminar el grupo {name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not self.store.delete_group(name):
            QMessageBox.warning(self, APP_NAME, "No se pudo eliminar el grupo.")
            return
        self._reload_table()
        self.on_changed()


class SatelliteListScreen(QWidget):
    back_clicked = pyqtSignal()

    def __init__(self, open_map_callback, parent: QWidget | None = None):
        super().__init__(parent)
        self.open_map_callback = open_map_callback
        self.store = SatelliteStore()
        self.conn = None
        self.pending_reload = False
        self.search_text = ""
        self.filter_groups: set[str] = set()
        self.filter_states: set[str] = set()
        self.sort_key = "name"
        self.sort_descending = False
        self.current_page = 1
        self.filtered_records: list[dict] = []
        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self._poll_for_changes)
        self._build_ui()
        self._refresh_table(force_sync=False)
        self._update_filters_button_state()

    def set_connection(self, conn) -> None:
        self.conn = conn
        if self.conn is not None and (
            self.store.current_game_uid == self.store._legacy_game_uid()
            or not self.store.visible_records()
        ):
            self._refresh_table(force_sync=True)
        self._poll_for_changes()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        header_panel = GlassPanel()
        header_layout = QHBoxLayout(header_panel)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(12)

        logo = QLabel()
        logo_pix = QPixmap(str(LOGO_PATH_CORT)) if LOGO_PATH_CORT.exists() else QPixmap()
        if not logo_pix.isNull():
            logo.setPixmap(logo_pix.scaledToWidth(180, Qt.TransformationMode.SmoothTransformation))
        else:
            logo.setText(APP_NAME)
            logo.setStyleSheet("color:#dce9f6; font-size:16px; font-weight:700;")
        header_layout.addWidget(logo)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar satélites por nombre")
        self.search_input.textChanged.connect(self._on_search_changed)
        header_layout.addWidget(self.search_input, 1)

        self.filters_button = QPushButton("Filtros")
        self.filters_button.setIcon(QIcon(_make_icon_pixmap("globe")))
        self.filters_button.clicked.connect(self._open_filters)
        header_layout.addWidget(self.filters_button)

        self.sort_button = QPushButton("Ordenar")
        self.sort_button.setIcon(QIcon(_make_icon_pixmap("reload")))
        self.sort_button.clicked.connect(self._open_sort)
        header_layout.addWidget(self.sort_button)

        self.groups_button = QPushButton("Grupos")
        self.groups_button.setIcon(QIcon(_make_icon_pixmap("edit")))
        self.groups_button.clicked.connect(self._open_groups)
        header_layout.addWidget(self.groups_button)

        self.reload_button = QPushButton("Recargar información")
        self.reload_button.setIcon(QIcon(_make_icon_pixmap("reload")))
        self.reload_button.setVisible(False)
        self.reload_button.clicked.connect(self._reload_from_ksp)
        header_layout.addWidget(self.reload_button)

        root.addWidget(header_panel)

        table_panel = GlassPanel()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(14, 14, 14, 14)
        table_layout.setSpacing(10)

        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels([
            "ID", "Nombre", "Descripción", "Grupo", "Órbita", "Inclinación",
            "Periodo orbital", "Excentricidad", "Fecha de lanzamiento",
            "Estado", "Multimedia", "Acciones",
        ])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setStyleSheet("""
            QTableWidget {
                background: rgba(10, 18, 28, 210);
                color: #e6eef7;
                gridline-color: rgba(126, 164, 196, 45);
                border: 1px solid rgba(126, 164, 196, 70);
                border-radius: 10px;
                selection-background-color: rgba(35, 88, 120, 120);
                selection-color: #f4fbff;
            }
            QTableWidget::item {
                padding: 8px 8px;
                border-bottom: 1px solid rgba(126, 164, 196, 28);
            }
            QTableWidget::item:selected {
                background: rgba(35, 88, 120, 130);
            }
            QHeaderView::section {
                background: rgba(15, 29, 43, 240);
                color: #f3f8fc;
                border: none;
                border-right: 1px solid rgba(126, 164, 196, 60);
                padding: 9px 8px;
                font-weight: 700;
            }
            QScrollBar:vertical {
                background: rgba(22, 27, 34, 140);
                width: 7px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #3a5670;
                border-radius: 3px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: #5b84a7;
            }
        """)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(11, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setWordWrap(True)
        self.table.cellClicked.connect(self._on_cell_clicked)
        table_layout.addWidget(self.table)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.page_info = QLabel("Página 1/1")
        self.page_info.setObjectName("muted")
        self.prev_page_btn = QPushButton("Anterior")
        self.prev_page_btn.clicked.connect(self._previous_page)
        self.next_page_btn = QPushButton("Siguiente")
        self.next_page_btn.clicked.connect(self._next_page)
        footer.addWidget(self.prev_page_btn)
        footer.addWidget(self.next_page_btn)
        footer.addWidget(self.page_info)
        footer.addStretch()
        back_btn = QPushButton("← Volver")
        back_btn.setObjectName("btnBack")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #FFFFFF;
                text-decoration: none;
            }
            QPushButton:hover {
                text-decoration: underline;
            }
        """)
        back_btn.clicked.connect(self._on_back_clicked)
        footer.addWidget(back_btn)
        table_layout.addLayout(footer)

        root.addWidget(table_panel, 1)

        self.loading_overlay = QWidget(self)
        self.loading_overlay.setStyleSheet("""
            QWidget {
                background: rgba(7, 17, 29, 180);
            }
        """)
        overlay_layout = QVBoxLayout(self.loading_overlay)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_layout.setSpacing(12)
        self.loading_spinner = SpinnerWidget(58)
        self.loading_label = QLabel("Sincronizando información...")
        self.loading_label.setObjectName("status")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addWidget(self.loading_spinner, alignment=Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addWidget(self.loading_label)
        self.loading_overlay.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "loading_overlay"):
            self.loading_overlay.setGeometry(self.rect())
            self.loading_overlay.raise_()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._check_timer.start(7000)
        self._poll_for_changes()

    def hideEvent(self, event) -> None:
        self._check_timer.stop()
        super().hideEvent(event)

    def _set_loading(self, visible: bool, message: str = "Sincronizando información...") -> None:
        self.loading_label.setText(message)
        self.loading_overlay.setVisible(visible)
        if visible:
            self.loading_overlay.raise_()
            QApplication.processEvents()

    def _on_search_changed(self, text: str) -> None:
        self.search_text = text.strip().lower()
        self.current_page = 1
        self._update_filters_button_state()
        self._refresh_table(force_sync=False)

    def _open_filters(self) -> None:
        dialog = SatelliteFilterDialog(
            groups=list(self.store.groups.keys()),
            selected_groups=self.filter_groups,
            selected_states=self.filter_states,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.filter_groups = dialog.selected_groups()
        self.filter_states = dialog.selected_states()
        self.current_page = 1
        self._update_filters_button_state()
        self._refresh_table(force_sync=False)

    def _open_sort(self) -> None:
        dialog = SatelliteSortDialog(self.sort_key, self.sort_descending, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.sort_key, self.sort_descending = dialog.result_payload()
        self.current_page = 1
        self._refresh_table(force_sync=False)

    def _open_groups(self) -> None:
        dialog = SatelliteGroupsDialog(self.store, self._on_groups_changed, parent=self)
        dialog.exec()

    def _on_groups_changed(self) -> None:
        valid_groups = set(self.store.groups.keys())
        self.filter_groups.intersection_update(valid_groups)
        self._update_filters_button_state()
        self._refresh_table(force_sync=False)

    def _reload_from_ksp(self) -> None:
        if self.conn is None:
            QMessageBox.information(self, APP_NAME, "La conexión con KSP no está disponible.")
            return
        self._set_loading(True, "Recargando información desde KSP...")
        try:
            self.store.sync_from_connection(self.conn)
        finally:
            self.pending_reload = False
            self.reload_button.setVisible(False)
            self._set_loading(False)
        self.current_page = 1
        self._refresh_table(force_sync=False)

    def _poll_for_changes(self) -> None:
        if self.conn is None:
            return
        current_sig = self.store.snapshot_signature(self.conn)
        pending = current_sig != self.store.last_signature
        self.pending_reload = pending
        self.reload_button.setVisible(pending)
        if pending and not self.isVisible():
            return
        if pending:
            self.reload_button.setToolTip("Hay cambios detectados en KSP. Pulsa para actualizar.")

    def _has_active_filters(self) -> bool:
        return bool(self.search_text or self.filter_groups or self.filter_states)

    def _update_filters_button_state(self) -> None:
        if self._has_active_filters():
            self.filters_button.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 140, 140, 110);
                    color: #fff1f1;
                    border: 1px solid rgba(255, 183, 183, 190);
                    border-radius: 9px;
                    padding: 8px 12px;
                }
                QPushButton:hover {
                    background: rgba(255, 155, 155, 140);
                    border-color: rgba(255, 196, 196, 230);
                }
            """)
        else:
            self.filters_button.setStyleSheet("")

    def _refresh_table(self, force_sync: bool = False) -> None:
        if force_sync and self.conn is not None:
            self._set_loading(True)
            try:
                self.store.sync_from_connection(self.conn)
            finally:
                self._set_loading(False)

        records = list(self.store.visible_records())
        if self.search_text:
            records = [record for record in records if self.search_text in record.get("name", "").lower()]
        if self.filter_groups:
            records = [
                record for record in records
                if self.filter_groups.intersection(set(record.get("groups", []) or []))
            ]
        if self.filter_states:
            records = [record for record in records if record.get("status") in self.filter_states]

        if self.sort_key == "launch":
            records.sort(key=lambda record: float(record.get("launch_ut") or 0.0), reverse=self.sort_descending)
        else:
            records.sort(key=lambda record: record.get("name", "").lower(), reverse=self.sort_descending)

        self.filtered_records = records
        total_pages = max(1, math.ceil(len(records) / SATELLITES_PAGE_SIZE))
        self.current_page = min(max(1, self.current_page), total_pages)
        start = (self.current_page - 1) * SATELLITES_PAGE_SIZE
        page_records = records[start:start + SATELLITES_PAGE_SIZE]

        self.table.setRowCount(len(page_records))
        for row, record in enumerate(page_records):
            self._populate_row(row, record)

        self.page_info.setText(f"Página {self.current_page}/{total_pages} · {len(records)} satélites")
        self.prev_page_btn.setEnabled(self.current_page > 1)
        self.next_page_btn.setEnabled(self.current_page < total_pages)

    def _populate_row(self, row: int, record: dict) -> None:
        orbit = record.get("orbit") or {}
        groups = record.get("groups") or []
        values = [
            str(record.get("id", "")),
            record.get("name", ""),
            _shorten_text(record.get("description", "") or "Sin descripción", 84),
            ", ".join(groups) if groups else record.get("group", ""),
            f"P {float(orbit.get('periapsis_km', 0) or 0):.0f} km / A {float(orbit.get('apoapsis_km', 0) or 0):.0f} km",
            f"{float(orbit.get('inclination_deg', 0.0) or 0.0):0.2f}°",
            self._format_period(float(orbit.get("period_s", 0.0) or 0.0)),
            f"{float(orbit.get('eccentricity', 0.0) or 0.0):0.4f}",
            record.get("launch_date") or _format_ksp_ut(record.get("launch_ut")),
            record.get("status", SATELLITE_STATUS_ACTIVE),
        ]

        for col in range(10):
            if col in (2, 9):
                continue
            item = QTableWidgetItem(values[col])
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, col, item)

        multimedia_btn = QPushButton()
        multimedia_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        multimedia_btn.setIcon(QIcon(_make_icon_pixmap("media")))
        multimedia_btn.setText(str(len(record.get("multimedia", []) or [])))
        multimedia_btn.setToolTip("Abrir multimedia")
        multimedia_btn.clicked.connect(lambda _=False, payload=record: self._open_media(payload))
        multimedia_btn.setEnabled(bool(record.get("multimedia")))
        multimedia_btn.setMinimumWidth(62)
        self.table.setCellWidget(row, 10, multimedia_btn)

        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(6)

        edit_btn = QPushButton()
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setToolTip("Editar")
        edit_btn.setIcon(QIcon(_make_icon_pixmap("edit")))
        edit_btn.setFixedSize(32, 28)
        edit_btn.clicked.connect(lambda _=False, payload=record: self._edit_satellite(payload))
        action_layout.addWidget(edit_btn)

        if record.get("status") != SATELLITE_STATUS_OFFLINE:
            map_btn = QPushButton()
            map_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            map_btn.setToolTip("Mapa satelital")
            map_btn.setIcon(QIcon(_make_icon_pixmap("globe")))
            map_btn.setFixedSize(32, 28)
            map_btn.clicked.connect(lambda _=False, payload=record: self._open_map(payload))
            action_layout.addWidget(map_btn)

        action_layout.addStretch()
        self.table.setCellWidget(row, 11, action_widget)

        status_text = record.get("status", SATELLITE_STATUS_ACTIVE)
        status_item = QTableWidgetItem(status_text)
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        status_item.setBackground(QBrush(QColor(self._status_color(status_text))))
        status_item.setForeground(QBrush(QColor("#f6fbff")))
        self.table.setItem(row, 9, status_item)

        desc_widget = ElidedClickableLabel(record.get("description", "") or "Sin descripción")
        desc_widget.setWordWrap(False)
        desc_widget.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        desc_widget.setStyleSheet("padding: 4px 6px; color: #dce9f6;")
        desc_widget.setToolTip(record.get("description", "") or "Sin descripción")
        desc_widget.clicked.connect(lambda payload=record: self._open_description(payload))
        self.table.setCellWidget(row, 2, desc_widget)
        self.table.setRowHeight(row, 52)

    def _status_color(self, status: str) -> str:
        if status == SATELLITE_STATUS_MAINTENANCE:
            return "#7baeff"
        if status == SATELLITE_STATUS_OFFLINE:
            return "#ff8383"
        return "#94f0bf"

    def _format_period(self, seconds: float) -> str:
        if seconds <= 0:
            return "—"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours:
            return f"{hours}h {minutes:02d}m {secs:02d}s"
        return f"{minutes}m {secs:02d}s"

    def _on_cell_clicked(self, row: int, column: int) -> None:
        if row < 0 or row >= len(self.filtered_records):
            return
        start = (self.current_page - 1) * SATELLITES_PAGE_SIZE
        record = self.filtered_records[start + row]
        if column == 2:
            self._open_description(record)
        elif column == 10 and record.get("multimedia"):
            self._open_media(record)

    def _open_description(self, record: dict) -> None:
        dialog = SatelliteDescriptionDialog(record, parent=self)
        dialog.exec()

    def _open_media(self, record: dict) -> None:
        if not record.get("multimedia"):
            return
        dialog = SatelliteMediaDialog(record, parent=self)
        dialog.exec()

    def _edit_satellite(self, record: dict) -> None:
        dialog = SatelliteEditDialog(self.store, record, list(self.store.groups.keys()), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dialog.result_payload()
        auto_groups = set(record.get("groups_auto") or [])
        selected_groups = set(payload["selected_groups"])
        manual_groups = [group for group in selected_groups if group not in auto_groups]
        normalized_media = self.store.normalize_multimedia_entries(int(record.get("id", 0)), payload["multimedia"])
        self.store.update_satellite(
            int(record.get("id", 0)),
            description=payload["description"],
            groups_manual=manual_groups,
            multimedia=normalized_media,
            status=payload["status"],
        )
        self._refresh_table(force_sync=False)

    def _open_map(self, record: dict) -> None:
        if record.get("status") == SATELLITE_STATUS_OFFLINE:
            return
        if self.open_map_callback is not None:
            self.open_map_callback(record.get("name", ""))

    def _previous_page(self) -> None:
        if self.current_page > 1:
            self.current_page -= 1
            self._refresh_table(force_sync=False)

    def _next_page(self) -> None:
        total_pages = max(1, math.ceil(len(self.filtered_records) / SATELLITES_PAGE_SIZE))
        if self.current_page < total_pages:
            self.current_page += 1
            self._refresh_table(force_sync=False)

    def _on_back_clicked(self) -> None:
        self.back_clicked.emit()



    def update_group(self, name: str, full_name: str, description: str) -> bool:
        group = self.groups.get(name)
        if not group or group.get("system"):
            return False
        group["full_name"] = full_name.strip() or name
        group["description"] = description.strip()
        self.save()
        return True

    def rename_group(self, old_name: str, new_name: str, full_name: str, description: str) -> bool:
        group = self.groups.get(old_name)
        new_key = new_name.strip().upper()
        if not group or group.get("system") or not new_key or (new_key != old_name and new_key in self.groups):
            return False
        if new_key != old_name:
            self.groups[new_key] = self.groups.pop(old_name)
            for record in self.records:
                if record.get("group") == old_name:
                    record["group"] = new_key
        group = self.groups[new_key]
        group["name"] = new_key
        group["full_name"] = full_name.strip() or new_key
        group["description"] = description.strip()
        self.save()
        return True

    def delete_group(self, name: str) -> bool:
        group = self.groups.get(name)
        if not group or group.get("system"):
            return False
        del self.groups[name]
        for record in self.records:
            if record.get("group") == name:
                orbit = record.get("orbit") or {}
                altitude = max(0.0, (float(orbit.get("periapsis_km", 0) or 0) + float(orbit.get("apoapsis_km", 0) or 0)) / 2.0)
                record["group"] = _auto_group_for_altitude(altitude)
                record["group_manual"] = False
        self.save()
        return True



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

    class PassthroughOverlay(QWidget):
        """Overlay transparente que reenvía eventos de mouse al GLViewWidget
        cuando el cursor no está encima de ningún widget hijo interactivo."""

        def __init__(self, view_widget, parent=None):
            super().__init__(parent)
            self._view = view_widget
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        def _hit_interactive_child(self, pos):
            """Devuelve True si pos (en coords del overlay) cae sobre un hijo interactivo."""
            child = self.childAt(pos)
            if child is None:
                return False
            # Recorrer la jerarquía hasta el overlay; si alguno es interactivo → True
            w = child
            while w is not None and w is not self:
                if isinstance(w, (QLineEdit, QPushButton, QFrame, QScrollArea)):
                    # QFrame incluye info_panel; solo bloqueamos si es visible
                    if isinstance(w, QFrame) and not w.isVisible():
                        w = w.parentWidget()
                        continue
                    return True
                w = w.parentWidget()
            return False

        def _forward_to_view(self, event):
            """Transforma el evento a coordenadas del view y lo envía."""
            from PyQt6.QtCore import QPointF
            global_pos = self.mapToGlobal(event.position().toPoint())
            view_pos = self._view.mapFromGlobal(global_pos)
            # Crear un evento sintético equivalente no es trivial en PyQt6;
            # en su lugar llamamos directamente al handler personalizado del visualizador.
            return view_pos

        def mousePressEvent(self, event):
            if not self._hit_interactive_child(event.position().toPoint()):
                # Crear evento equivalente en el view y llamar al handler
                from PyQt6.QtGui import QMouseEvent
                global_pos = self.mapToGlobal(event.position().toPoint())
                view_local = self._view.mapFromGlobal(global_pos)
                new_event = QMouseEvent(
                    event.type(),
                    QPointF(view_local),
                    event.globalPosition(),
                    event.button(),
                    event.buttons(),
                    event.modifiers(),
                )
                self._view.mousePressEvent(new_event)
                return
            super().mousePressEvent(event)

        def mouseReleaseEvent(self, event):
            if not self._hit_interactive_child(event.position().toPoint()):
                from PyQt6.QtGui import QMouseEvent
                global_pos = self.mapToGlobal(event.position().toPoint())
                view_local = self._view.mapFromGlobal(global_pos)
                new_event = QMouseEvent(
                    event.type(),
                    QPointF(view_local),
                    event.globalPosition(),
                    event.button(),
                    event.buttons(),
                    event.modifiers(),
                )
                self._view.mouseReleaseEvent(new_event)
                return
            super().mouseReleaseEvent(event)

        def mouseMoveEvent(self, event):
            if not self._hit_interactive_child(event.position().toPoint()):
                from PyQt6.QtCore import QPointF
                from PyQt6.QtGui import QMouseEvent
                global_pos = self.mapToGlobal(event.position().toPoint())
                view_local = self._view.mapFromGlobal(global_pos)
                new_event = QMouseEvent(
                    event.type(),
                    QPointF(view_local),
                    event.globalPosition(),
                    event.button(),
                    event.buttons(),
                    event.modifiers(),
                )
                self._view.mouseMoveEvent(new_event)
                return
            super().mouseMoveEvent(event)

        def wheelEvent(self, event):
            if not self._hit_interactive_child(event.position().toPoint()):
                from PyQt6.QtCore import QPointF
                from PyQt6.QtGui import QWheelEvent
                global_pos = self.mapToGlobal(event.position().toPoint())
                view_local = self._view.mapFromGlobal(global_pos)
                new_event = QWheelEvent(
                    QPointF(view_local),
                    event.globalPosition(),
                    event.pixelDelta(),
                    event.angleDelta(),
                    event.buttons(),
                    event.modifiers(),
                    event.phase(),
                    event.inverted(),
                )
                self._view.wheelEvent(new_event)
                return
            super().wheelEvent(event)

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
            self._press_vessel = None

            self._build_ui()
            self._init_static_scene()

            self.timer = QTimer(self)
            self.timer.timeout.connect(self._update_orbits)

            # Timer de animación: extrapola posiciones Keplerianas entre
            # actualizaciones del servidor para lograr un movimiento fluido (~33 FPS).
            self.animation_timer = QTimer(self)
            self.animation_timer.timeout.connect(self._animate_satellites)

            self.vessels_to_update = []
            self.current_vessel_index = 0

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
            from PyQt6.QtWidgets import QSizePolicy, QLayout # <--- Añadido para controlar el tamaño

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
            self.overlay = PassthroughOverlay(self.view, self)
            self.overlay.setFixedWidth(260)

            # Le damos un fondo oscuro, borde y esquinas redondeadas idénticas a tus otros paneles
            self.overlay.setStyleSheet("""
                PassthroughOverlay, QWidget {
                    background: rgba(13, 17, 23, 180);
                    border-radius: 8px;
                }
                QLineEdit, QFrame, QLabel, QPushButton {
                    background: transparent; /* Evita que los hijos hereden el fondo de forma incorrecta */
                }
            """)

            # Forzamos a que el layout ajuste el contenedor al tamaño mínimo de sus elementos (Logo + Buscador)
            overlay_layout = QVBoxLayout(self.overlay)
            overlay_layout.setContentsMargins(12, 14, 12, 14)
            overlay_layout.setSpacing(10)
            overlay_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

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

            # overlay_layout.addStretch()  <--- ELIMINADO para evitar que empuje y expanda el menú

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
                f"<span style='color:{c_val}'>{vel_ms:.0f} m/s</span>"
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
            self.timer.start(300)
            self.animation_timer.start(30)

        def _on_connect_failed(self, err: str):
            pass  # Sin UI de estado visible

        def _disconnect(self):
            self.timer.stop()
            self.animation_timer.stop()
            self._clear_all_vessels()

            if self.conn:
                try:
                    self.conn.close()
                except Exception:
                    pass
                self.conn = None

            self._camera_fitted = False

        def _clear_all_vessels(self):
            if hasattr(self, 'animation_timer'):
                self.animation_timer.stop()
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
            self.animation_timer.stop()
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

            highlighted_items = []

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
                        line_width = 3.5
                        dot_color = obj.get('base_dot_color')
                        trail_visible = True
                    else:
                        line_color = (0.02, 0.07, 0.09, 0.08)  # Muy atenuado para no competir con la orbita resaltada
                        line_width = 1.0
                        base_dot = obj.get('base_dot_color')
                        if base_dot is not None:
                            dot_color = (base_dot[0]*0.16, base_dot[1]*0.16, base_dot[2]*0.16, 0.2)
                        else:
                            dot_color = (0.16, 0.16, 0.16, 0.2)
                        trail_visible = False  # Ocultar rastro para limpiar la escena
                else:
                    line_color = obj.get('base_line_color', ORBIT_LINE_COLOR)
                    line_width = 3.5 if is_selected else 1.5
                    dot_color = obj.get('base_dot_color')
                    trail_visible = show_in_map

                if line is not None:
                    line.setVisible(show_in_map)
                    if show_in_map and line_color is not None:
                        line.setData(pos=obj['orbit_pts'], color=line_color, width=line_width)
                        if is_hovered or is_selected:
                            highlighted_items.append(line)

                if dot is not None:
                    dot.setVisible(show_in_map)
                    if show_in_map and dot_color is not None:
                        dot.setData(pos=np.array([obj['pos_3d']], dtype=np.float32), color=dot_color)
                        if is_hovered or is_selected:
                            highlighted_items.append(dot)

                if trail is not None:
                    trail.setVisible(trail_visible)
                    if trail_visible:
                        trail_colors = obj.get('trail_colors')
                        ordered = obj.get('ordered_trail')
                        if trail_colors is not None and ordered is not None:
                            trail.setData(pos=ordered, color=trail_colors)
                        if is_hovered or is_selected:
                            highlighted_items.append(trail)

            # PyQtGraph pinta los GL items en orden de insercion; reinsertar el destacado
            # evita que una orbita atenuada de la misma trayectoria se mezcle por encima.
            for item in highlighted_items:
                try:
                    self.view.removeItem(item)
                    self.view.addItem(item)
                except Exception:
                    pass

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

            self._load_all_vessels_initially()
            # Refrescar panel de info si hay selección activa (no reinicia la orientación)
            if self.selected_vessel is not None and self.selected_vessel in self.render_objects:
                self._update_info_panel(self.selected_vessel)
                self._focus_camera_on(self.selected_vessel, initial=False)

        def _load_all_vessels_initially(self):
            if not self.conn:
                return

            try:
                active_vids = set()
                theta = np.linspace(0, 2 * np.pi, ORBIT_POINTS)
                cos_t = np.cos(theta)
                sin_t = np.sin(theta)
                max_orbit_radius = KERBIN_RADIUS_KM

                vessels = list(self.conn.space_center.vessels)

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
                                'R_matrix': R,
                                'r_orbit': r_orbit,
                                'ecc': ecc,
                                'period': period,
                                'true_anomaly_base': true_anom,
                                'last_update_time': time.time(),
                            }
                        else:
                            obj = self.render_objects[vid]
                            now_t = time.time()
                            resolved_anom = self._resolve_server_anomaly(obj, true_anom, ecc, period, now_t)
                            if resolved_anom != true_anom:
                                r_now2 = r_orbit * (1 - ecc**2) / (1 + ecc * np.cos(resolved_anom))
                                pos_now2 = (R @ np.array([
                                    r_now2 * np.cos(resolved_anom),
                                    r_now2 * np.sin(resolved_anom),
                                    0.0
                                ]))
                                sx, sy, sz = float(pos_now2[0]), float(pos_now2[1]), float(pos_now2[2])

                            obj['orbit_pts'] = rotated
                            obj['pos_3d'] = (sx, sy, sz)
                            obj['info_data'] = info_data
                            obj['R_matrix'] = R
                            obj['r_orbit'] = r_orbit
                            obj['ecc'] = ecc
                            obj['period'] = period
                            obj['true_anomaly_base'] = resolved_anom
                            obj['last_update_time'] = now_t

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
                                ordered = buf[:head + 1] if head > 0 else buf[:1]

                            obj['ordered_trail'] = ordered

                    except Exception:
                        continue

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

                if not self._camera_fitted and active_vids:
                    target_distance = max(5200.0, max_orbit_radius * 1.5)
                    self.view.setCameraPosition(distance=target_distance)
                    self._camera_fitted = True

                self._update_selection_visuals()

                # Guardar naves activas para actualizar secuencialmente
                self.vessels_to_update = [v for v in vessels if v.name in active_vids]
                self.current_vessel_index = 0

            except Exception as e:
                self._handle_update_error(e)

        def _update_orbits(self):
            if not self.conn:
                return

            try:
                # Si hemos recorrido todas las naves, solicitamos los datos globales (número de satélites / cambios)
                if not hasattr(self, 'vessels_to_update') or not self.vessels_to_update or self.current_vessel_index >= len(self.vessels_to_update):
                    vessels = list(self.conn.space_center.vessels)
                    active_vids = set()

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
                        except Exception:
                            continue

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

                    self.vessels_to_update = [v for v in vessels if v.name in active_vids]
                    self.current_vessel_index = 0
                    self._update_selection_visuals()

                if not self.vessels_to_update:
                    return

                # Actualizar el siguiente satélite
                vessel = self.vessels_to_update[self.current_vessel_index]
                self.current_vessel_index += 1

                vid = vessel.name
                if vid not in self.vessel_streams or vid not in self.render_objects:
                    return

                streams = self.vessel_streams[vid]
                sma = streams['sma']()
                inc = streams['inc']()
                lan = streams['lan']()
                argp = streams['argp']()
                ecc = streams['ecc']()
                period = streams['period']()
                r_orbit = sma / 1000.0

                theta = np.linspace(0, 2 * np.pi, ORBIT_POINTS)
                cos_t = np.cos(theta)
                sin_t = np.sin(theta)

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

                obj = self.render_objects[vid]
                now_t = time.time()
                resolved_anom = self._resolve_server_anomaly(obj, true_anom, ecc, period, now_t)
                if resolved_anom != true_anom:
                    r_now2 = r_orbit * (1 - ecc**2) / (1 + ecc * np.cos(resolved_anom))
                    pos_now2 = (R @ np.array([
                        r_now2 * np.cos(resolved_anom),
                        r_now2 * np.sin(resolved_anom),
                        0.0
                    ]))
                    sx, sy, sz = float(pos_now2[0]), float(pos_now2[1]), float(pos_now2[2])

                obj['orbit_pts'] = rotated
                obj['pos_3d'] = (sx, sy, sz)
                obj['info_data'] = info_data
                obj['R_matrix'] = R
                obj['r_orbit'] = r_orbit
                obj['ecc'] = ecc
                obj['period'] = period
                obj['true_anomaly_base'] = resolved_anom
                obj['last_update_time'] = now_t

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
                    ordered = buf[:head + 1] if head > 0 else buf[:1]

                obj['ordered_trail'] = ordered

                if self.selected_vessel == vid:
                    self._update_info_panel(vid)
                    self._focus_camera_on(vid, initial=False)

                self._update_selection_visuals()

            except Exception as e:
                self._handle_update_error(e)

        def _propagate_true_anomaly(self, ecc, period, ta_base, dt):
            """Devuelve la anomalía verdadera tras `dt` segundos a partir de
            `ta_base`, usando movimiento medio Kepleriano. Reutilizado tanto
            por la animación de cada frame como por la corrección anti-salto
            cuando llega un dato real del servidor."""
            if dt < 0:
                dt = 0.0
            n = 2.0 * math.pi / period  # movimiento medio (rad/s)

            if ecc < 0.999:
                E0 = 2.0 * math.atan2(
                    math.sqrt(max(0.0, 1 - ecc)) * math.sin(ta_base / 2.0),
                    math.sqrt(max(1e-12, 1 + ecc)) * math.cos(ta_base / 2.0)
                )
                M0 = E0 - ecc * math.sin(E0)
                M = M0 + n * dt
                M = math.fmod(M, 2.0 * math.pi)

                # Resolver la ecuación de Kepler M = E - e*sin(E) (Newton-Raphson)
                E = M
                for _ in range(6):
                    f = E - ecc * math.sin(E) - M
                    fp = 1.0 - ecc * math.cos(E)
                    if abs(fp) < 1e-12:
                        break
                    E = E - f / fp

                return 2.0 * math.atan2(
                    math.sqrt(max(0.0, 1 + ecc)) * math.sin(E / 2.0),
                    math.sqrt(max(1e-12, 1 - ecc)) * math.cos(E / 2.0)
                )
            else:
                # Órbitas hiperbólicas / parabólicas: extrapolación lineal simple
                return ta_base + n * dt

        def _resolve_server_anomaly(self, obj, true_anom, ecc, period, now_t):
            """Concilia el dato real recibido del servidor con la posición ya
            extrapolada localmente, evitando que el satélite 'retroceda'
            visualmente por jitter o latencia de los streams de krpc.

            Si el dato del servidor queda por detrás de donde ya habíamos
            extrapolado (caso típico: la llamada al stream tarda unos ms y
            trae un estado ligeramente más antiguo que 'ahora'), se conserva
            la posición ya extrapolada y se sigue avanzando desde ahí. Si el
            servidor va por delante (p. ej. tras una maniobra real), se
            adopta directamente el nuevo valor.
            """
            prev_ta_base = obj.get('true_anomaly_base')
            prev_t0 = obj.get('last_update_time')
            prev_ecc = obj.get('ecc')
            prev_period = obj.get('period')

            if prev_ta_base is None or prev_t0 is None or not prev_period:
                return true_anom

            try:
                dt_prev = now_t - prev_t0
                predicted = self._propagate_true_anomaly(
                    prev_ecc if prev_ecc is not None else ecc,
                    prev_period, prev_ta_base, dt_prev
                )
                diff = math.atan2(
                    math.sin(true_anom - predicted),
                    math.cos(true_anom - predicted)
                )
                # diff < 0  => el dato del servidor va "por detrás" de lo ya
                # mostrado: ignoramos el retroceso y mantenemos la posición
                # extrapolada para no producir un salto hacia atrás visible.
                if diff < 0:
                    return predicted
                return true_anom
            except Exception:
                return true_anom

        def _animate_satellites(self):
            """Extrapola la posición de cada satélite a partir de su última
            actualización real usando física Kepleriana (movimiento medio),
            de forma que el movimiento se vea continuo y fluido a ~33 FPS,
            sin importar cuántos satélites haya ni el orden en que el
            servidor los vaya actualizando."""
            if not self.render_objects:
                return

            now = time.time()
            selected = self.selected_vessel

            for vid, obj in self.render_objects.items():
                try:
                    R = obj.get('R_matrix')
                    r_orbit = obj.get('r_orbit')
                    ecc = obj.get('ecc')
                    period = obj.get('period')
                    ta_base = obj.get('true_anomaly_base')
                    t0 = obj.get('last_update_time')

                    if (R is None or r_orbit is None or ecc is None
                            or not period or ta_base is None or t0 is None):
                        continue

                    dt = now - t0
                    true_anom = self._propagate_true_anomaly(ecc, period, ta_base, dt)

                    r_now = r_orbit * (1 - ecc ** 2) / (1 + ecc * math.cos(true_anom))
                    x_now = r_now * math.cos(true_anom)
                    y_now = r_now * math.sin(true_anom)
                    pos_now = R @ np.array([x_now, y_now, 0.0])
                    sx, sy, sz = float(pos_now[0]), float(pos_now[1]), float(pos_now[2])

                    obj['pos_3d'] = (sx, sy, sz)

                    show_in_map = selected is None or selected == vid
                    dot = obj.get('dot')
                    if dot is not None and show_in_map:
                        dot.setData(pos=np.array([[sx, sy, sz]], dtype=np.float32))

                except Exception:
                    continue

            # Seguimiento de cámara fluido sobre el satélite seleccionado
            if selected is not None and selected in self.render_objects:
                self._focus_camera_on(selected, initial=False)

        def _handle_update_error(self, e):
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
                self._press_pos = event.position()
                self._press_vessel = hit[0] if hit is not None else None
                self.is_rotating = True
                self.last_mouse_pos = event.position()
                if hit is not None:
                    return
                # Guardar posición del press para distinguir click de drag
                self._press_pos = event.position()
                self.is_rotating = True
                self.last_mouse_pos = event.position()

        def _mouse_release(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                self.is_rotating = False
                # Solo deseleccionar si fue un click puro (sin arrastre)
                if self._press_pos is not None:
                    delta = event.position() - self._press_pos
                    is_click = (delta.x() ** 2 + delta.y() ** 2) < 16  # < 4px de movimiento
                    release_hit = self._vessel_at_cursor(event)

                    if (
                        is_click and
                        self._press_vessel is not None and
                        release_hit is not None and
                        release_hit[0] == self._press_vessel
                    ):
                        self._select_vessel(self._press_vessel)
                    elif is_click and self._press_vessel is None and self.selected_vessel is not None:
                        self._deselect_vessel()
                self._press_pos = None
                self._press_vessel = None
                self.last_mouse_pos = None

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
        self.resize(1120, 800)
        self.setMinimumSize(800, 560)

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

        self.satellite_list = SatelliteListScreen(self._open_orbital_map_from_list)
        self.stack.addWidget(self.satellite_list)
        self.satellite_list.back_clicked.connect(self.show_command_center)

        self.press_module = PressModuleScreen(self.show_command_center)
        self.stack.addWidget(self.press_module)

    # ── Callbacks de conexión KSP ──────────────────────────────────────────────

    def _on_ksp_connected(self, conn) -> None:
        """Recibe la conexión KSP establecida desde el hilo de background."""
        self._ksp_conn = conn
        self._ksp_error = None
        if self.visualizer is not None:
            self.visualizer.set_connection(conn)
        if self.satellite_list is not None:
            self.satellite_list.set_connection(conn)

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
        if module_name in {"Mapa orbital", "Lista de satélites", "Notas de prensa"}:
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
        if module_name == "Lista de satélites":
            self._launch_satellite_list()
            return
        if module_name == "Notas de prensa":
            self._launch_press_notes()
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

    def _launch_orbital_map(self, vessel_name: str | None = None) -> None:
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
        if vessel_name:
            QTimer.singleShot(0, lambda: self.visualizer._select_vessel(vessel_name))
        self.statusBar().showMessage("Mapa orbital iniciado", 5000)

    def _launch_satellite_list(self) -> None:
        if self.satellite_list is None:
            QMessageBox.critical(self, APP_NAME, "La lista de satélites no está disponible.")
            self.show_command_center()
            return
        if self._ksp_conn is not None:
            self.satellite_list.set_connection(self._ksp_conn)
        self.stack.setCurrentWidget(self.satellite_list)
        fade_in(self.satellite_list, 650)
        self.statusBar().showMessage("Lista de satélites iniciada", 5000)

    def _open_orbital_map_from_list(self, vessel_name: str) -> None:
        self._launch_orbital_map(vessel_name)

    def _launch_press_notes(self) -> None:
        if self.press_module is None:
            QMessageBox.critical(self, APP_NAME, "El módulo de notas de prensa no está disponible.")
            self.show_command_center()
            return
        self.stack.setCurrentWidget(self.press_module)
        self.press_module.start()
        fade_in(self.press_module, 650)
        self.statusBar().showMessage("Notas de prensa iniciadas", 5000)

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
    QComboBox, QTextEdit, QListWidget {
        background: rgba(9, 20, 32, 210);
        color: #eef7fb;
        border: 1px solid rgba(126, 164, 196, 90);
        border-radius: 9px;
        selection-background-color: #2e83a6;
        selection-color: #f3fbff;
    }
    QComboBox {
        padding: 8px 12px;
    }
    QComboBox::drop-down {
        border: none;
        width: 24px;
    }
    QComboBox QAbstractItemView, QListWidget {
        background: #0b1621;
        color: #eef7fb;
        border: 1px solid rgba(126, 164, 196, 90);
        outline: 0;
    }
    QCheckBox {
        color: #dce9f6;
        spacing: 8px;
    }
    QToolButton {
        background: transparent;
        border: 1px solid transparent;
    }
    QToolButton:hover {
        border-color: rgba(126, 164, 196, 80);
        background: rgba(13, 28, 43, 130);
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
    QWidget#moduleCard,
    QWidget#moduleCardDisabled {
        background: rgba(10, 18, 28, 140);
        border: 1px solid rgba(123, 168, 198, 70);
        border-radius: 16px;
    }
    QWidget#moduleCard {
        border-color: rgba(129, 215, 244, 120);
    }
    QWidget#moduleCard:hover {
        border-color: rgba(157, 231, 255, 190);
        background: rgba(12, 22, 33, 170);
    }
    QWidget#moduleCardDisabled {
        border-color: rgba(95, 121, 142, 60);
        background: rgba(8, 14, 22, 120);
    }
    QWidget#moduleCardDisabled QLabel#moduleCardTitle,
    QWidget#moduleCardDisabled QLabel#moduleCardSubtitle {
        color: rgba(190, 205, 216, 160);
    }
    QWidget#moduleCardImagePanel {
        background: #08111b;
        border-top-left-radius: 16px;
        border-top-right-radius: 16px;
    }
    QWidget#moduleCardTextPanel {
        background: rgba(18, 22, 28, 170);
        border-bottom-left-radius: 16px;
        border-bottom-right-radius: 16px;
        border-top: 1px solid rgba(120, 162, 190, 55);
    }
    QLabel#moduleCardTitle {
        color: #f0f7fb;
        font-size: 18px;
        font-weight: 800;
        letter-spacing: 0.2px;
    }
    QLabel#moduleCardSubtitle {
        color: #9cb0bf;
        font-size: 12px;
        font-weight: 600;
    }
    QWidget#moduleCard:hover QLabel#moduleCardTitle {
        color: #ffffff;
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
    QFrame#saveContextCard {
        background: rgba(12, 22, 34, 226);
        border: 1px solid rgba(126, 164, 196, 84);
        border-radius: 12px;
    }
    QFrame#saveContextCard[state="active"] {
        border-color: rgba(111, 196, 233, 160);
        background: rgba(14, 27, 40, 236);
    }
    QFrame#saveContextCard[state="empty"] {
        border-color: rgba(255, 179, 179, 120);
        background: rgba(32, 18, 22, 224);
    }
    QFrame#pressCard {
        background: rgba(14, 24, 36, 214);
        border: 1px solid rgba(126, 164, 196, 88);
        border-left: 3px solid transparent;
        border-radius: 16px;
    }
    QFrame#pressCard:hover,
    QFrame#pressCard[hovered="true"] {
        background: rgba(8, 16, 25, 255);
        border-color: rgba(137, 213, 241, 240);
        border-left: 4px solid rgba(137, 213, 241, 245);
    }
    QFrame#pressSeparator {
        background: rgba(126, 164, 196, 165);
        min-height: 1px;
        max-height: 1px;
        border: none;
        margin: 0px 18px;
    }
    QToolButton#pressMenuButton {
        background: rgba(12, 21, 32, 220);
        color: #edf6fb;
        border: 1px solid rgba(126, 164, 196, 95);
        border-radius: 17px;
        padding: 0px;
        font-size: 18px;
        font-weight: 800;
    }
    QToolButton#pressMenuButton:hover {
        background: rgba(23, 37, 51, 250);
        border-color: rgba(137, 213, 241, 220);
        color: #ffffff;
    }
    QToolButton#pressMenuButton:pressed {
        background: rgba(32, 51, 70, 255);
        border-color: rgba(163, 230, 248, 235);
    }
    QToolButton#pressMenuButton::menu-indicator {
        image: none;
        width: 0px;
    }
    QMenu#pressNoteMenu {
        background: rgba(9, 16, 24, 248);
        color: #edf6fb;
        border: 1px solid rgba(126, 164, 196, 110);
        border-radius: 10px;
        padding: 4px;
    }
    QMenu#pressNoteMenu::item {
        padding: 8px 18px;
        margin: 2px 2px;
        border-radius: 8px;
        background: transparent;
    }
    QMenu#pressNoteMenu::item:selected,
    QMenu#pressNoteMenu::item:hover {
        background: rgba(23, 37, 51, 255);
        color: #ffffff;
    }
    QFrame#pressBlock {
        background: rgba(12, 22, 34, 225);
        border: 1px solid rgba(126, 164, 196, 80);
        border-radius: 14px;
    }
    QPushButton#pressAttachmentButton {
        text-align: left;
        background: rgba(13, 23, 35, 210);
        color: #e9f3fa;
        border: 1px solid rgba(126, 164, 196, 84);
        border-left: 3px solid transparent;
        border-radius: 11px;
        padding: 10px 14px;
        font-size: 13px;
        font-weight: 700;
        text-decoration: none;
        margin: 0px 0px 6px 0px;
    }
    QPushButton#pressAttachmentButton:hover {
        background: rgba(24, 42, 60, 242);
        border-color: rgba(137, 213, 241, 220);
        border-left: 3px solid rgba(137, 213, 241, 235);
        color: #ffffff;
        text-decoration: underline;
    }
    QPushButton#pressAttachmentButton:pressed {
        background: rgba(30, 52, 73, 245);
        border-color: rgba(163, 230, 248, 210);
        border-left: 3px solid rgba(163, 230, 248, 240);
    }
    QPushButton#pressFab {
        background: #1d6f91;
        color: #f3fbff;
        border: 1px solid #66c7e8;
        border-radius: 29px;
        font-size: 26px;
        font-weight: 700;
    }
    QPushButton#pressFab:hover {
        background: #2585aa;
        border-color: #9ee4f5;
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