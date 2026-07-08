"""
Common repository for Terranova Aerospace project.

Contains utility functions, constants, database/store persistence layers,
and shared UI widgets.
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

from PyQt6.QtCore import (
    QEasingCurve, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, QThread,
    pyqtSignal, pyqtProperty, QDate, QPoint, QPointF, QEvent, QByteArray, QBuffer
)
from PyQt6.QtGui import (
    QMouseEvent, QAction, QColor, QDesktopServices, QIcon, QPainter, QPen,
    QPixmap, QPalette, QFont, QCursor, QVector3D, QFontMetrics, QBrush,
    QTextCursor, QTextDocument
)
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QHeaderView, QListWidget, QListWidgetItem,
    QPushButton, QRadioButton, QScrollArea, QSpinBox, QSizePolicy, QDateEdit,
    QTableWidget, QTableWidgetItem, QTextEdit, QTextBrowser, QStackedWidget,
    QMenu, QToolButton, QRubberBand, QVBoxLayout, QWidget
)
from PySide6.QtCore import QVariantAnimation

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
    "Programación": "internal",  # cambiado a internal para conectar los stubs
    "Centro de mando": "internal",
    "Personal": "internal",
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
    "SATÉLITES LUNARES": {
        "name": "SATÉLITES LUNARES",
        "full_name": "Satélites Lunares",
        "description": "Satélites que orbitan la Luna",
        "min_alt_km": None,
        "max_alt_km": None,
        "system": True,
    },
}

SATELLITE_GROUP_LUNAR = "SATÉLITES LUNARES"

# Nombres (normalizados en minúsculas) que identifican a la Luna como cuerpo
# orbitado. Cubre KSP estándar ("Mun"), Real Solar System ("Moon") y guardados
# traducidos ("Luna"). Añade aquí otras variantes si tu partida usa otro nombre.
LUNAR_BODY_NAMES = {"mun", "moon", "luna"}


def _is_lunar_body(body_name: str) -> bool:
    return _normalize_key(str(body_name or "")) in LUNAR_BODY_NAMES


def apply_shadow(widget: QWidget, blur: int = 28, alpha: int = 90) -> None:
    # Se elimina el efecto de sombreado (remarcado oscuro) para dejar la interfaz plana
    pass


def fade_in(widget: QWidget, duration: int = 700) -> None:
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
        
        # 1. TAMAÑO FIJO ABSOLUTO: Bloquea las dimensiones de la card a 330x330 px
        self.setFixedSize(330, 330)
        
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 2. DISTRIBUCIÓN INTERNA INTERNA FIJA (Ejemplo: 230px imagen + 100px texto = 330px total)
        self.image_panel = ModuleCardImagePanel(self._load_pixmap())
        self.image_panel.setObjectName("moduleCardImagePanel")
        self.image_panel.setFixedHeight(230) 
        root.addWidget(self.image_panel)

        self.text_panel = QFrame()
        self.text_panel.setObjectName("moduleCardTextPanel")
        self.text_panel.setFixedHeight(100)
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

    # Nota: Ya NO necesitas el método resizeEvent(), puedes borrarlo si lo habías añadido.

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


# ─── Funciones Auxiliares Notas de Prensa ──────────────────────────────────────

def _press_date_sort_key(value: str) -> tuple[int, int, int, int]:
    date_obj = QDate.fromString(value, "yyyy-MM-dd")
    if not date_obj.isValid():
        date_obj = QDate.fromString(value, "dd/MM/yyyy")
    if not date_obj.isValid():
        return (0, 0, 0, 0)
    return (date_obj.year(), date_obj.month(), date_obj.day(), 1)


def _press_plain_text_from_html(html_str: str) -> str:
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", html_str, flags=re.IGNORECASE | re.DOTALL)
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
            html_str = str(block.get("html") or "")
            plain = str(block.get("plain") or _press_plain_text_from_html(html_str)).strip()
            text_parts.append(html_str.strip() or plain)
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


def _resolve_press_path(value: str) -> Path:
    if not value:
        return Path()
    path = Path(value)
    if path.is_absolute():
        return path
    return (BASE_DIR / path).resolve()


# ─── Funciones Auxiliares Satélites y KSP ─────────────────────────────────────

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


# ─── Clases del visualizador orbital en tiempo real (QThread) ─────────────────

if _KSP_AVAILABLE:
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
else:
    class ConnectThread(QThread):  # type: ignore
        pass

    def connect_to_ksp_async(on_success, on_failure):  # type: ignore
        return None


# ─── Data Stores ──────────────────────────────────────────────────────────────

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

    def _orbit_similarity_score(self, left: dict, right: dict) -> float:
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

    def _groups_for_orbit_body(self, body_name: str) -> list[str]:
        if _is_lunar_body(body_name):
            return [SATELLITE_GROUP_LUNAR]
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

            _orbit_body = orbit.get("body", "")
            _lunar_grp  = self._groups_for_orbit_body(_orbit_body)
            if not groups_auto:
                groups_auto = [_auto_group_for_altitude(float(orbit.get("apoapsis_km", 0) or 0))]
                groups_auto += _lunar_grp
            else:
                # Re-evaluar siempre el grupo lunar aunque groups_auto ya esté poblado
                groups_auto = [g for g in groups_auto if g != SATELLITE_GROUP_LUNAR]
                groups_auto += _lunar_grp
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
                body_obj = getattr(orbit, "body", None)
                body_name = str(getattr(body_obj, "name", "") or "").strip()
                orbit_payload = {
                    "periapsis_km": round(periapsis_km, 3),
                    "apoapsis_km": round(apoapsis_km, 3),
                    "inclination_deg": round(math.degrees(float(getattr(orbit, "inclination", 0.0) or 0.0)), 6),
                    "period_s": round(float(getattr(orbit, "period", 0.0) or 0.0), 3),
                    "eccentricity": round(float(getattr(orbit, "eccentricity", 0.0) or 0.0), 6),
                    "body": body_name,
                }
                snapshots.append({
                    "name": name,
                    "periapsis_km": orbit_payload["periapsis_km"],
                    "apoapsis_km": orbit_payload["apoapsis_km"],
                    "inclination_deg": orbit_payload["inclination_deg"],
                    "period_s": orbit_payload["period_s"],
                    "eccentricity": orbit_payload["eccentricity"],
                    "body": body_name,
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
                *self._groups_for_orbit_body(sat.get("body", "")),
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
                "body": sat.get("body", ""),
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


# ─── Programación Store ───────────────────────────────────────────────────────

PROGRAMACION_FILE = CONFIG_DIR / "programacion.json"

MANIOBRA_TYPES = [
    "Lanzamiento",
    "Desorbitamiento",
    "Acople",
    "Modificación de órbita",
]


class ProgramacionStore:
    """Persistence layer for scheduled manoeuvres/launches."""

    def __init__(self, data_file: Path = PROGRAMACION_FILE):
        self.data_file = data_file
        self.records: list[dict] = []
        self.next_id = 1
        self.load()

    def load(self) -> None:
        payload = _load_json_file(self.data_file, {})
        if isinstance(payload, dict):
            self.next_id = int(payload.get("next_id", 1))
            raw = payload.get("records", [])
            self.records = [r for r in raw if isinstance(r, dict)]
        else:
            self.next_id = 1
            self.records = []

    def save(self) -> None:
        _save_json_file(self.data_file, {
            "next_id": self.next_id,
            "records": self.records,
        })

    def _allocate_id(self) -> int:
        rid = self.next_id
        self.next_id += 1
        return rid

    def get_all(self) -> list[dict]:
        return list(self.records)

    def get_by_id(self, record_id: int) -> dict | None:
        for r in self.records:
            if int(r.get("id", 0)) == int(record_id):
                return r
        return None

    def add(self, objeto: str, maniobra: str, detalles: str, fecha: str) -> dict:
        record = {
            "id": self._allocate_id(),
            "objeto": str(objeto).strip(),
            "maniobra": str(maniobra).strip(),
            "detalles": str(detalles).strip(),
            "fecha": str(fecha).strip(),
            "created_at": time.time(),
        }
        self.records.append(record)
        self.save()
        return record

    def update(self, record_id: int, objeto: str, maniobra: str, detalles: str, fecha: str) -> bool:
        record = self.get_by_id(record_id)
        if record is None:
            return False
        record["objeto"] = str(objeto).strip()
        record["maniobra"] = str(maniobra).strip()
        record["detalles"] = str(detalles).strip()
        record["fecha"] = str(fecha).strip()
        self.save()
        return True

    def delete(self, record_id: int) -> bool:
        before = len(self.records)
        self.records = [r for r in self.records if int(r.get("id", 0)) != int(record_id)]
        if len(self.records) == before:
            return False
        self.save()
        return True


# ─── Personal Store ───────────────────────────────────────────────────────────

PERSONAL_FILE = CONFIG_DIR / "personal.json"


class PersonalStore:
    """Persistence layer for staff/personnel management."""

    def __init__(self, data_file: Path = PERSONAL_FILE):
        self.data_file = data_file
        self.records: list[dict] = []
        self.next_id = 1
        self.load()

    def load(self) -> None:
        payload = _load_json_file(self.data_file, {})
        if isinstance(payload, dict):
            self.next_id = int(payload.get("next_id", 1))
            raw = payload.get("records", [])
            self.records = [r for r in raw if isinstance(r, dict)]
        else:
            self.next_id = 1
            self.records = []

    def save(self) -> None:
        _save_json_file(self.data_file, {
            "next_id": self.next_id,
            "records": self.records,
        })

    def _allocate_id(self) -> int:
        rid = self.next_id
        self.next_id += 1
        return rid

    def get_all(self) -> list[dict]:
        return list(self.records)

    def get_by_id(self, record_id: int) -> dict | None:
        for r in self.records:
            if int(r.get("id", 0)) == int(record_id):
                return r
        return None

    def query(self, text: str = "") -> list[dict]:
        term = _normalize_key(text)
        results = list(self.records)
        if term:
            results = [
                r for r in results
                if term in _normalize_key(r.get("nombre", ""))
                or term in _normalize_key(r.get("apellidos", ""))
                or term in str(r.get("edad", ""))
            ]
        return results

    def add(self, nombre: str, apellidos: str, edad: str, puesto: str) -> dict:
        record = {
            "id": self._allocate_id(),
            "nombre": str(nombre).strip(),
            "apellidos": str(apellidos).strip(),
            "edad": str(edad).strip(),
            "puesto": str(puesto).strip(),
            "created_at": time.time(),
        }
        self.records.append(record)
        self.save()
        return record

    def update(self, record_id: int, nombre: str, apellidos: str, edad: str, puesto: str) -> bool:
        record = self.get_by_id(record_id)
        if record is None:
            return False
        record["nombre"] = str(nombre).strip()
        record["apellidos"] = str(apellidos).strip()
        record["edad"] = str(edad).strip()
        record["puesto"] = str(puesto).strip()
        self.save()
        return True

    def delete(self, record_id: int) -> bool:
        before = len(self.records)
        self.records = [r for r in self.records if int(r.get("id", 0)) != int(record_id)]
        if len(self.records) == before:
            return False
        self.save()
        return True