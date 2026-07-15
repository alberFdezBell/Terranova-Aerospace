"""
Centro de Mando — NavBall/MFD Panel for Kerbal Space Program via kRPC.

Provides a real-time instrument panel inspired by KSP's NavBall and MFD
displays, including flight data, orbital info, resource monitoring, engine
status, target tracking, and vessel controls.
"""

from __future__ import annotations

import math
from typing import Any
import base64
import time
import re
import socket
import os
import urllib.request
import urllib.error
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

from PyQt6.QtCore import (
    pyqtSignal, Qt, QTimer, QRectF, QPointF, QThread, QMutex, QWaitCondition,
    QUrl, QByteArray
)
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont, QLinearGradient, QPainterPath, QPixmap, QImage
)
from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QScrollArea, QSlider, QMainWindow, QSizePolicy, QCheckBox,
    QListWidget, QListWidgetItem, QGroupBox, QDialog, QDialogButtonBox,
    QProgressBar
)
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage

from core_shared import (
    GlassPanel, fade_in
)

# ──────────────────────────────────────────────────────────────────────────────
# Página web personalizada para interceptar navegación a jrti://
# ──────────────────────────────────────────────────────────────────────────────

class _JRTIPage(QWebEnginePage):
    """Página web que intercepta el esquema jrti:// para ejecutar acciones Python."""

    folder_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def acceptNavigationRequest(self, url: QUrl, _type: QWebEnginePage.NavigationType, isMainFrame: bool) -> bool:
        if url.scheme() == "jrti":
            if url.host() == "open-recordings":
                self.folder_requested.emit()
            return False  # No navegamos realmente
        return super().acceptNavigationRequest(url, _type, isMainFrame)

# ──────────────────────────────────────────────────────────────────────────────
# Servidor HTTP de telemetría (sirve datos kRPC al frontend web)
# ──────────────────────────────────────────────────────────────────────────────

_telemetry_data = {}
_telemetry_mutex = QMutex()


class TelemetryHTTPRequestHandler(BaseHTTPRequestHandler):
    """Manejador HTTP que sirve la telemetría actual como JSON."""

    def do_GET(self):
        if self.path == "/telemetry":
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            _telemetry_mutex.lock()
            data = dict(_telemetry_data)
            _telemetry_mutex.unlock()
            self.wfile.write(json.dumps(data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Silenciar logs del servidor HTTP


def _start_telemetry_server(port: int = 8090):
    """Inicia el servidor HTTP de telemetría en un hilo separado."""
    server = HTTPServer(("127.0.0.1", port), TelemetryHTTPRequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[TelemetryServer] Escuchando en http://127.0.0.1:{port}/telemetry")
    return server

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

COLOR_BG_DARK = QColor("#0a1622")
COLOR_PANEL_BG = QColor(10, 22, 34, 200)
COLOR_TEXT = QColor("#dce9f6")
COLOR_TEXT_MUTED = QColor("#91a8bb")
COLOR_ACCENT = QColor("#6fc4e9")
COLOR_GREEN = QColor("#4ecca3")
COLOR_RED = QColor("#ff5e5e")
COLOR_ORANGE = QColor("#f0a030")
COLOR_YELLOW = QColor("#f0d060")
COLOR_BUTTON_ACTIVE = QColor("#1d6f91")
COLOR_BUTTON_INACTIVE = QColor("#2a3a4a")
COLOR_BAR_BG = QColor(20, 40, 60, 180)
COLOR_NAVBALL_BG = QColor("#0d1a28")
COLOR_NAVBALL_RING = QColor("#2a4a6a")

FONT_DIGITS = "Consolas, 'Courier New', monospace"
FONT_LABEL = "Segoe UI, Arial, sans-serif"

FONT_DIGITS_FAMILY = "Consolas"
FONT_LABEL_FAMILY = "Segoe UI"

SAS_MODES = [
    ("Stability Assist", "stability_assist"),
    ("Prograde",         "prograde"),
    ("Retrograde",       "retrograde"),
    ("Normal",           "normal"),
    ("Anti-Normal",      "anti_normal"),
    ("Radial In",        "radial_in"),
    ("Radial Out",       "radial_out"),
    ("Target",           "target"),
    ("Anti-Target",      "anti_target"),
    ("Maneuver",         "maneuver"),
]

RESOURCE_NAMES = {
    "ElectricCharge":  ("⚡ EC",     COLOR_YELLOW),
    "LiquidFuel":      ("⛽ LF",     COLOR_ORANGE),
    "Oxidizer":        ("💧 Ox",     COLOR_ACCENT),
    "Monopropellant":  ("◈ Mono",    COLOR_GREEN),
}

# ──────────────────────────────────────────────────────────────────────────────
# Ventana para mostrar la interfaz web de JRTI
# ──────────────────────────────────────────────────────────────────────────────

class JRTIWebViewWindow(QMainWindow):
    """Ventana que muestra la interfaz web del mod JRTI."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("JRTI - Just Read The Instructions")
        self.setMinimumSize(1024, 768)
        self.setStyleSheet("background-color: #0a1622;")
        
        # Widget central
        central_widget = QWidget()
        central_widget.setStyleSheet("background-color: #0a1622;")
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Barra de navegación simple
        nav_bar = QWidget()
        nav_bar.setStyleSheet("""
            QWidget {
                background-color: #0d1a28;
                border-bottom: 1px solid rgba(126, 164, 196, 40);
            }
        """)
        nav_bar.setFixedHeight(40)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(10, 5, 10, 5)
        
        # Botón de recarga
        reload_btn = QPushButton("🔄 Recargar")
        reload_btn.setStyleSheet("""
            QPushButton {
                background: #1d6f91;
                color: #dce9f6;
                border: 1px solid rgba(126, 164, 196, 80);
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #2585aa;
            }
        """)
        reload_btn.clicked.connect(self._reload_page)
        nav_layout.addWidget(reload_btn)
        
        # Botón de carpeta de grabaciones (solo visible en recorder.html)
        self.btn_folder = QPushButton("📁 Grabaciones")
        self.btn_folder.setStyleSheet("""
            QPushButton {
                background: #2a5a3a;
                color: #dce9f6;
                border: 1px solid rgba(126, 164, 196, 80);
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #3a7a4a;
            }
        """)
        self.btn_folder.setVisible(False)
        self.btn_folder.clicked.connect(self._open_recordings_folder)
        nav_layout.addWidget(self.btn_folder)
        
        nav_layout.addStretch()
        
        # Indicador de estado
        self.status_label = QLabel("Cargando JRTI...")
        self.status_label.setStyleSheet("color: #91a8bb; font-size: 11px; font-family: 'Segoe UI';")
        nav_layout.addWidget(self.status_label)
        
        nav_layout.addStretch()
        
        # Botón de cerrar
        close_btn = QPushButton("✕ Cerrar")
        close_btn.setStyleSheet("""
            QPushButton {
                background: #5a2a2a;
                color: #dce9f6;
                border: 1px solid rgba(200, 80, 80, 60);
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #7a3a3a;
            }
        """)
        close_btn.clicked.connect(self.close)
        nav_layout.addWidget(close_btn)
        
        layout.addWidget(nav_bar)
        
        # WebView
        self.web_view = QWebEngineView()
        self.web_view.setStyleSheet("background-color: #0a1622;")
        
        # Usar página personalizada que intercepta jrti://open-recordings
        self._jrti_page = _JRTIPage(self.web_view)
        self._jrti_page.folder_requested.connect(self._open_recordings_folder)
        self.web_view.setPage(self._jrti_page)
        
        self.web_view.load(QUrl("http://localhost:8081/"))
        
        # Conectar señales para estado de carga y detección de URL
        self.web_view.loadFinished.connect(self._on_load_finished)
        self.web_view.loadProgress.connect(self._on_load_progress)
        self.web_view.urlChanged.connect(self._on_url_changed)
        
        # Timer de respaldo para verificar la URL periódicamente
        self._url_check_timer = QTimer(self)
        self._url_check_timer.timeout.connect(self._check_url_for_folder_button)
        self._url_check_timer.setInterval(1000)  # cada 1 segundo
        self._url_check_timer.start()
        
        layout.addWidget(self.web_view)
        
    def _check_url_for_folder_button(self):
        """Verifica periódicamente la URL actual para mostrar/ocultar el botón de carpeta."""
        try:
            current_url = self.web_view.url().toString()
            if "recorder.html" in current_url:
                if not self.btn_folder.isVisible():
                    self.btn_folder.setVisible(True)
                    self._inject_folder_button_handler()
            else:
                if self.btn_folder.isVisible():
                    self.btn_folder.setVisible(False)
        except Exception:
            pass
        
    def _on_url_changed(self, url: QUrl):
        """Detecta cambios de URL para mostrar/ocultar el botón de carpeta."""
        url_str = url.toString()
        if "recorder.html" in url_str:
            self.btn_folder.setVisible(True)
            self._inject_folder_button_handler()
        else:
            self.btn_folder.setVisible(False)
    
    def _inject_folder_button_handler(self):
        """Inyecta JavaScript para que el botón de carpeta de la web use os.startfile de Python."""
        js = """
        (function() {
            var btn = document.getElementById('recorder-folder-btn');
            if (btn && !btn._jrtiHandlerInjected) {
                btn._jrtiHandlerInjected = true;
                btn.addEventListener('click', function(e) {
                    e.preventDefault();
                    window.location.href = 'jrti://open-recordings';
                });
            }
        })();
        """
        self.web_view.page().runJavaScript(js)
        
    def _open_recordings_folder(self):
        """Abre la carpeta de grabaciones de JRTI en el explorador de Windows."""
        folder_path = r"C:\Program Files\Epic Games\KerbalSpaceProgram\Spanish\GameData\JustReadTheInstructions\Web\recordings"
        try:
            if os.path.exists(folder_path):
                os.startfile(folder_path)
            else:
                self.status_label.setText(f"❌ Carpeta no encontrada: {folder_path}")
        except Exception as e:
            self.status_label.setText(f"❌ Error al abrir carpeta: {str(e)[:30]}")
        
    def _reload_page(self):
        """Recarga la página web."""
        self.status_label.setText("Recargando...")
        self.web_view.reload()
        
    def _on_load_finished(self, success: bool):
        """Callback cuando la página termina de cargar."""
        if success:
            self.status_label.setText("✅ JRTI cargado correctamente")
            # Verificar la URL actual para mostrar/ocultar botón de carpeta
            current_url = self.web_view.url().toString()
            if "recorder.html" in current_url:
                self.btn_folder.setVisible(True)
                self._inject_folder_button_handler()
            else:
                self.btn_folder.setVisible(False)
        else:
            self.status_label.setText("❌ Error al cargar JRTI - ¿Está el servidor ejecutándose?")
            
    def _on_load_progress(self, progress: int):
        """Callback del progreso de carga."""
        if progress < 100:
            self.status_label.setText(f"Cargando JRTI... {progress}%")
            
    def closeEvent(self, event):
        """Cierra la ventana y limpia recursos."""
        self._url_check_timer.stop()
        self.web_view.stop()
        self.web_view.setPage(None)
        super().closeEvent(event)


# ──────────────────────────────────────────────────────────────────────────────
# Actualización de telemetría para el servidor HTTP (llamado desde el loop principal)
# ──────────────────────────────────────────────────────────────────────────────

telemetry_server_instance = None

def ensure_telemetry_server():
    """Asegura que el servidor de telemetría esté funcionando (se llama una vez)."""
    global telemetry_server_instance
    if telemetry_server_instance is None:
        telemetry_server_instance = _start_telemetry_server(8090)

def update_telemetry_data(dp: 'CommandCenterDataProvider'):
    """Actualiza los datos de telemetría desde el provider de kRPC."""
    global _telemetry_data, _telemetry_mutex
    _telemetry_mutex.lock()
    try:
        alt_m = dp.get("altitude", 0.0)
        spd_ms = dp.get("speed", 0.0)
        vessel_name = dp.vessel_name
        situation = dp.get("situation", None)
        _telemetry_data = {
            "altitude_km": round(alt_m / 1000.0, 2),
            "velocity_kmh": round(spd_ms * 3.6, 1),
            "velocity_ms": round(spd_ms, 1),
            "vessel_name": vessel_name if vessel_name else "—",
            "situation": str(situation) if situation else "—",
            "timestamp": time.time(),
        }
    except Exception:
        _telemetry_data = {
            "altitude_km": 0.0,
            "velocity_kmh": 0.0,
            "velocity_ms": 0.0,
            "vessel_name": "—",
            "situation": "—",
            "timestamp": time.time(),
        }
    finally:
        _telemetry_mutex.unlock()

# ──────────────────────────────────────────────────────────────────────────────
# HTTP Video Stream Fetcher (CORREGIDO)
# ──────────────────────────────────────────────────────────────────────────────

class HttpStreamFetcher(QThread):
    """Thread para obtener frames de video desde streams HTTP de JRTI."""
    
    frame_received = pyqtSignal(QPixmap)
    status_changed = pyqtSignal(str)
    streams_discovered = pyqtSignal(list)
    scan_progress = pyqtSignal(int, int)  # current, total
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        super().__init__()
        self._base_url = base_url
        self._running = False
        self._mutex = QMutex()
        self._wait_condition = QWaitCondition()
        self._frame_interval = 1/60
        self._active_stream_id: int = 0
        self._available_streams: list[dict] = []
        self._stream_discovery_done = False
        self._consecutive_errors = 0
        self._last_frame_time = 0
        self._camera_range_start = 0
        self._camera_range_end = 106
        self._is_scanning = False
        self._should_stop_scan = False
        
        # Cache de conexiones
        self._connection_cache: dict[int, bool] = {}

        # Si True, se usa una lista de streams fijada externamente
        self._use_fixed_streams = False
        
        # Buffer para MJPEG
        self._mjpeg_buffer = b""
        self._boundary = b""
        self._is_mjpeg = False

        # Conexión HTTP persistente al stream activo
        self._current_response = None
        self._current_conn_id: int | None = None
        self._chunk_size = 8192
        self._read_timeout = 5
        
    def set_base_url(self, url: str):
        self._base_url = url
        
    def set_camera_range(self, start: int, end: int):
        self._camera_range_start = start
        self._camera_range_end = end
        
    def set_active_stream(self, stream_id: int):
        self._active_stream_id = stream_id
        self._mjpeg_buffer = b""
        self._boundary = b""
        self._is_mjpeg = False

    def set_streams(self, streams: list[dict]):
        """Fija manualmente la lista de streams disponibles."""
        self._available_streams = list(streams)
        self._stream_discovery_done = True
        self._use_fixed_streams = True
        self._is_scanning = False
        if self._available_streams and self._active_stream_id not in {
            s.get('id') for s in self._available_streams
        }:
            self._active_stream_id = self._available_streams[0].get('id', 0)

    def get_available_streams(self) -> list[dict]:
        if not self._stream_discovery_done:
            self._discover_streams()
        return self._available_streams
        
    def check_camera_available(self, camera_id: int) -> bool:
        """Verifica si una cámara específica está disponible."""
        if camera_id in self._connection_cache:
            return self._connection_cache[camera_id]
            
        url = f"{self._base_url}/camera/{camera_id}/stream"
        available = self._check_stream_available(url)
        self._connection_cache[camera_id] = available
        return available
        
    def _discover_streams(self):
        """Descubre streams HTTP disponibles en el rango especificado."""
        self._available_streams = []
        self._stream_discovery_done = False
        self._is_scanning = True
        self._should_stop_scan = False
        
        total = self._camera_range_end - self._camera_range_start + 1
        found = 0
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 3
        
        self.status_changed.emit(f"Escaneando cámaras {self._camera_range_start}-{self._camera_range_end}...")
        
        for camera_id in range(self._camera_range_start, self._camera_range_end + 1):
            if not self._running or self._should_stop_scan:
                break
                
            url = f"{self._base_url}/camera/{camera_id}/stream"
            
            available = self._check_stream_available(url)
            self._connection_cache[camera_id] = available
            
            if available:
                self._available_streams.append({
                    'id': camera_id,
                    'url': url,
                    'name': f"Cámara {camera_id}",
                    'port': 8080,
                    'available': True
                })
                found += 1
                consecutive_failures = 0
                self.status_changed.emit(f"Encontrada cámara {camera_id}")
            else:
                consecutive_failures += 1
                if found > 0 and consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    self.status_changed.emit(f"Deteniendo escaneo después de {consecutive_failures} fallos consecutivos")
                    self._should_stop_scan = True
                    break
            
            progress = camera_id - self._camera_range_start + 1
            self.scan_progress.emit(progress, total)
            
            self._wait_condition.wait(self._mutex, 10)
        
        self._is_scanning = False
        self._stream_discovery_done = True
        
        stream_names = [s.get('name', f"Cámara {s.get('id', 0)}") for s in self._available_streams]
        self.streams_discovered.emit(stream_names)
        self.status_changed.emit(f"Encontrados {len(self._available_streams)} streams HTTP")
        
    def _check_stream_available(self, url: str) -> bool:
        """Verifica si un stream HTTP está disponible usando GET con timeout corto."""
        try:
            req = urllib.request.Request(url, method='GET')
            req.add_header('User-Agent', 'Mozilla/5.0')
            req.add_header('Connection', 'close')
            
            try:
                with urllib.request.urlopen(req, timeout=1.5) as response:
                    status = response.getcode()
                    if status == 200:
                        data = response.read(1024)
                        if data:
                            return True
                        return True
                    return False
            except urllib.error.HTTPError as e:
                if e.code == 200:
                    return True
                return False
            except (urllib.error.URLError, socket.timeout, ConnectionRefusedError):
                return False
            except Exception:
                return False
                
        except Exception:
            return False
            
    def run(self):
        self._running = True
        
        if not self._use_fixed_streams:
            self._discover_streams()
        
        while self._running:
            try:
                if not self._available_streams:
                    self._consecutive_errors += 1
                    if self._consecutive_errors % 30 == 0:
                        self._discover_streams()
                    self._wait_condition.wait(self._mutex, 1000)
                    continue
                    
                self._fetch_frame()
                
                elapsed = time.time() - self._last_frame_time
                sleep_time = max(0, self._frame_interval - elapsed)
                if sleep_time > 0:
                    self._wait_condition.wait(self._mutex, int(sleep_time * 1000))
                    
            except Exception as e:
                self._consecutive_errors += 1
                if self._consecutive_errors % 10 == 0:
                    self.status_changed.emit(f"Error: {str(e)[:40]}")
                self._wait_condition.wait(self._mutex, 500)
                
        self._running = False
        
    def _fetch_frame(self):
        """Obtiene un frame del stream HTTP activo."""
        if not self._available_streams:
            return
            
        active_stream = None
        for stream in self._available_streams:
            if stream.get('id') == self._active_stream_id:
                active_stream = stream
                break
                
        if active_stream is None and self._available_streams:
            active_stream = self._available_streams[0]
            self._active_stream_id = active_stream.get('id', 0)
            
        if active_stream is None:
            return
            
        url = active_stream.get('url')
        if not url:
            return

        if self._current_response is None or self._current_conn_id != self._active_stream_id:
            self._close_connection()
            try:
                req = urllib.request.Request(url)
                req.add_header('User-Agent', 'Mozilla/5.0')
                req.add_header('Cache-Control', 'no-cache')
                self._current_response = urllib.request.urlopen(req, timeout=self._read_timeout)
                self._current_conn_id = self._active_stream_id
                self._mjpeg_buffer = b""
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    active_stream['available'] = False
                    self.status_changed.emit(f"Stream {self._active_stream_id} no disponible (404)")
                self._close_connection()
                return
            except Exception as e:
                self._consecutive_errors += 1
                if self._consecutive_errors % 10 == 0:
                    self.status_changed.emit(f"Error conectando: {str(e)[:30]}")
                self._close_connection()
                return

        try:
            chunk = self._current_response.read(self._chunk_size)
            if not chunk:
                self._close_connection()
                return

            self._mjpeg_buffer += chunk
            if len(self._mjpeg_buffer) > 2_000_000:
                self._mjpeg_buffer = self._mjpeg_buffer[-500_000:]

            pixmap = self._process_mjpeg_buffer()
            if pixmap is not None and not pixmap.isNull():
                self.frame_received.emit(pixmap)
                self._consecutive_errors = 0
                self._last_frame_time = time.time()

        except socket.timeout:
            pass
        except Exception as e:
            self._consecutive_errors += 1
            if self._consecutive_errors % 10 == 0:
                self.status_changed.emit(f"Error leyendo stream: {str(e)[:30]}")
            self._close_connection()

    def _close_connection(self):
        """Cierra la conexión HTTP persistente actual."""
        if self._current_response is not None:
            try:
                self._current_response.close()
            except Exception:
                pass
        self._current_response = None
        self._current_conn_id = None
                
    def _process_mjpeg_buffer(self) -> QPixmap | None:
        """Procesa el buffer MJPEG para extraer un frame completo."""
        data = self._mjpeg_buffer
        
        start_marker = b'\xff\xd8'
        end_marker = b'\xff\xd9'
        
        start_pos = data.find(start_marker)
        if start_pos == -1:
            return None
            
        end_pos = data.find(end_marker, start_pos + 2)
        if end_pos == -1:
            return None
            
        jpeg_data = data[start_pos:end_pos + 2]
        
        self._mjpeg_buffer = data[end_pos + 2:]
        
        return self._bytes_to_pixmap(jpeg_data)
                
    def _parse_mjpeg_data(self, data: bytes) -> QPixmap | None:
        """Parsea datos MJPEG para extraer un frame."""
        start_marker = b'\xff\xd8'
        end_marker = b'\xff\xd9'
        
        start_pos = data.find(start_marker)
        if start_pos == -1:
            return None
            
        end_pos = data.find(end_marker, start_pos + 2)
        if end_pos == -1:
            return None
            
        jpeg_data = data[start_pos:end_pos + 2]
        return self._bytes_to_pixmap(jpeg_data)
        
    def _bytes_to_pixmap(self, data: bytes) -> QPixmap | None:
        """Convierte datos de imagen en bytes a QPixmap."""
        try:
            qbyte = QByteArray(data)
            pixmap = QPixmap()
            if pixmap.loadFromData(qbyte):
                return pixmap
            return None
        except Exception:
            return None
            
    def stop(self):
        self._running = False
        self._should_stop_scan = True
        self._close_connection()
        self._wait_condition.wakeAll()
        self.wait()


# ──────────────────────────────────────────────────────────────────────────────
# Dialogo para seleccionar cámaras
# ──────────────────────────────────────────────────────────────────────────────

class CameraSelectionDialog(QDialog):
    """Diálogo para seleccionar cámaras disponibles."""
    
    cameras_selected = pyqtSignal(list)
    
    def __init__(self, parent=None, base_url="http://localhost:8080"):
        super().__init__(parent)
        self.setWindowTitle("SELECCIÓN DE CÁMARAS")
        self.setMinimumSize(450, 550)
        self.setStyleSheet("""
            QDialog {
                background-color: #0a1622;
                color: #dce9f6;
            }
            QLabel {
                color: #dce9f6;
            }
            QPushButton {
                background: #1d6f91;
                color: #dce9f6;
                border: 1px solid rgba(126, 164, 196, 80);
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 700;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #2585aa;
            }
            QPushButton:disabled {
                background: #1a2838;
                color: #5a6a7a;
            }
            QProgressBar {
                border: 1px solid rgba(126, 164, 196, 50);
                border-radius: 4px;
                background: #1a2a3a;
                height: 20px;
            }
            QProgressBar::chunk {
                background: #1d6f91;
                border-radius: 4px;
            }
            QCheckBox {
                color: #dce9f6;
                spacing: 8px;
                padding: 4px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid rgba(126, 164, 196, 60);
                background: #1a2a3a;
            }
            QCheckBox::indicator:checked {
                background: #1d6f91;
                border-color: #6fc4e9;
            }
            QCheckBox::indicator:hover {
                border-color: #6fc4e9;
            }
        """)
        
        self._base_url = base_url
        self._available_cameras: list[dict] = []
        self._checkboxes: dict[int, QCheckBox] = {}
        self._fetcher: HttpStreamFetcher | None = None
        self._is_scanning = False
        
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        title = QLabel("🔍 SELECCIÓN DE CÁMARAS")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #6fc4e9;")
        layout.addWidget(title)
        
        info = QLabel("Escanea las cámaras disponibles (se detiene tras 3 fallos consecutivos)")
        info.setStyleSheet("color: #91a8bb; font-size: 11px;")
        layout.addWidget(info)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 107)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        btn_layout = QHBoxLayout()
        
        self.scan_btn = QPushButton("🔍 ESCANEAR CÁMARAS")
        self.scan_btn.clicked.connect(self._start_scan)
        btn_layout.addWidget(self.scan_btn)
        
        self.select_all_btn = QPushButton("✅ SELECCIONAR TODAS")
        self.select_all_btn.clicked.connect(self._select_all)
        self.select_all_btn.setEnabled(False)
        btn_layout.addWidget(self.select_all_btn)
        
        self.deselect_all_btn = QPushButton("❌ DESELECCIONAR TODAS")
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        self.deselect_all_btn.setEnabled(False)
        btn_layout.addWidget(self.deselect_all_btn)
        
        layout.addLayout(btn_layout)
        
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                background: #0d1a28;
                border: 1px solid rgba(126, 164, 196, 40);
                border-radius: 4px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 4px;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background: rgba(29, 111, 145, 30);
            }
        """)
        layout.addWidget(self.list_widget)
        
        self.status_label = QLabel("Listo para escanear")
        self.status_label.setStyleSheet("color: #91a8bb; font-size: 10px;")
        layout.addWidget(self.status_label)
        
        button_box = QDialogButtonBox()
        self.ok_btn = button_box.addButton("✅ OK", QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_btn = button_box.addButton("❌ Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        self.ok_btn.setEnabled(False)
        self.ok_btn.clicked.connect(self._on_ok)
        self.cancel_btn.clicked.connect(self.reject)
        layout.addWidget(button_box)
        
    def _start_scan(self):
        if self._is_scanning:
            return
            
        self._is_scanning = True
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("🔍 ESCANEANDO...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Escaneando cámaras...")
        
        self.list_widget.clear()
        self._checkboxes.clear()
        self._available_cameras.clear()
        self.select_all_btn.setEnabled(False)
        self.deselect_all_btn.setEnabled(False)
        self.ok_btn.setEnabled(False)
        
        self._fetcher = HttpStreamFetcher(self._base_url)
        self._fetcher.set_camera_range(0, 106)
        self._fetcher.streams_discovered.connect(self._on_streams_discovered)
        self._fetcher.scan_progress.connect(self._on_scan_progress)
        self._fetcher.status_changed.connect(self._on_scan_status)
        self._fetcher.start()
        
    def _on_scan_progress(self, current: int, total: int):
        self.progress_bar.setValue(current)
        self.status_label.setText(f"Escaneando: {current}/{total}")
        
    def _on_scan_status(self, status: str):
        self.status_label.setText(status)
        
    def _on_streams_discovered(self, stream_names: list[str]):
        if self._fetcher is None:
            return
            
        self._available_cameras = self._fetcher.get_available_streams()
        
        self.list_widget.clear()
        self._checkboxes.clear()
        
        for cam in self._available_cameras:
            camera_id = cam.get('id', 0)
            name = cam.get('name', f"Cámara {camera_id}")
            
            item = QListWidgetItem()
            checkbox = QCheckBox(f"{name} (ID: {camera_id})")
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(lambda state, cid=camera_id: self._on_checkbox_changed(cid, state))
            self._checkboxes[camera_id] = checkbox
            
            item.setSizeHint(checkbox.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, checkbox)
        
        self.select_all_btn.setEnabled(len(self._available_cameras) > 0)
        self.deselect_all_btn.setEnabled(len(self._available_cameras) > 0)
        self.ok_btn.setEnabled(len(self._available_cameras) > 0)
        
        self.status_label.setText(f"Encontradas {len(self._available_cameras)} cámaras")
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("🔍 RE-ESCANEAR")
        self.progress_bar.setVisible(False)
        self._is_scanning = False
        
    def _on_checkbox_changed(self, camera_id: int, state: int):
        pass
        
    def _select_all(self):
        for checkbox in self._checkboxes.values():
            checkbox.setChecked(True)
            
    def _deselect_all(self):
        for checkbox in self._checkboxes.values():
            checkbox.setChecked(False)
            
    def _on_ok(self):
        selected = []
        for camera_id, checkbox in self._checkboxes.items():
            if checkbox.isChecked():
                for cam in self._available_cameras:
                    if cam.get('id') == camera_id:
                        selected.append(cam)
                        break
                        
        if selected:
            self.cameras_selected.emit(selected)
            self.accept()
        else:
            self.status_label.setText("⚠ Debes seleccionar al menos una cámara")
            
    def closeEvent(self, event):
        if self._fetcher is not None:
            self._fetcher.stop()
            self._fetcher = None
        super().closeEvent(event)


# ──────────────────────────────────────────────────────────────────────────────
# Thread para streaming de video (CORREGIDO)
# ──────────────────────────────────────────────────────────────────────────────

class VideoStreamThread(QThread):
    """Thread para recibir frames de video desde kRPC/JRTI (HTTP)."""
    
    frame_received = pyqtSignal(QPixmap)
    error_occurred = pyqtSignal(str)
    camera_changed = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    streams_discovered = pyqtSignal(list)
    
    def __init__(self, conn=None):
        super().__init__()
        self._conn = conn
        self._running = False
        self._mutex = QMutex()
        self._wait_condition = QWaitCondition()
        self._frame_interval = 1/60
        self._active_camera_name = ""
        self._last_frame_time = 0
        self._consecutive_errors = 0
        
        self._http_fetcher: HttpStreamFetcher | None = None
        self._use_http = True
        self._available_streams: list[dict] = []
        self._active_stream_index: int = -1
        self._stream_discovery_done = False
        self._base_url = "http://localhost:8080"
        self._selected_cameras: list[dict] = []
        
    def set_connection(self, conn):
        self._conn = conn
        
    def set_base_url(self, url: str):
        self._base_url = url
        if self._http_fetcher:
            self._http_fetcher.set_base_url(url)
        
    def set_camera(self, camera_name: str):
        self._mutex.lock()
        self._active_camera_name = camera_name
        self._mutex.unlock()
        self.camera_changed.emit(camera_name)
        
    def set_selected_cameras(self, cameras: list[dict]):
        self._selected_cameras = cameras
        self._available_streams = cameras.copy()
        self._stream_discovery_done = True
        
        if self._available_streams:
            self._active_stream_index = 0
            first = self._available_streams[0]
            self._active_camera_name = first.get('name', f"Cámara {first.get('id', 0)}")
            
        if self._http_fetcher:
            self._http_fetcher.set_streams(self._available_streams)
                
        stream_names = [s.get('name', f"Cámara {s.get('id', 0)}") for s in self._available_streams]
        self.streams_discovered.emit(stream_names)
        self.status_changed.emit(f"Configuradas {len(self._available_streams)} cámaras")
        
    def get_available_streams(self) -> list[dict]:
        return self._available_streams
    
    def get_stream_names(self) -> list[str]:
        return [s.get('name', 'Unknown') for s in self._available_streams]
    
    def set_active_stream_by_index(self, index: int) -> bool:
        if 0 <= index < len(self._available_streams):
            self._active_stream_index = index
            stream_info = self._available_streams[index]
            self._active_camera_name = stream_info.get("name", f"Stream {index}")
            camera_id = stream_info.get('id', 0)
            
            if self._http_fetcher:
                self._http_fetcher.set_active_stream(camera_id)
                
            self.camera_changed.emit(self._active_camera_name)
            return True
        return False
    
    def set_active_stream_by_name(self, name: str) -> bool:
        for i, stream in enumerate(self._available_streams):
            if stream.get('name') == name:
                return self.set_active_stream_by_index(i)
        return False
    
    def _on_http_frame(self, pixmap: QPixmap):
        if pixmap is not None and not pixmap.isNull():
            self.frame_received.emit(pixmap)
            self._consecutive_errors = 0
            self._last_frame_time = time.time()
        
    def _on_http_status(self, status: str):
        self.status_changed.emit(f"HTTP: {status}")
        
    def _on_http_streams(self, stream_names: list):
        self.streams_discovered.emit(stream_names)
        
    def run(self):
        self._running = True
        
        if self._http_fetcher is None:
            self._http_fetcher = HttpStreamFetcher(self._base_url)
            self._http_fetcher.frame_received.connect(self._on_http_frame)
            self._http_fetcher.status_changed.connect(self._on_http_status)
            self._http_fetcher.streams_discovered.connect(self._on_http_streams)
            
        if self._selected_cameras:
            self.set_selected_cameras(self._selected_cameras)
            
        if not self._http_fetcher.isRunning():
            self._http_fetcher.start()
            
        self.status_changed.emit("Stream HTTP iniciado")
            
        while self._running:
            try:
                self._wait_condition.wait(self._mutex, 100)
            except Exception as e:
                self._consecutive_errors += 1
                if self._consecutive_errors % 10 == 0:
                    self.status_changed.emit(f"Error: {str(e)[:40]}")
                self._wait_condition.wait(self._mutex, 500)
                
        self._running = False
        
    def stop(self):
        self._running = False
        if self._http_fetcher:
            self._http_fetcher.stop()
        self._wait_condition.wakeAll()
        self.wait()


# ──────────────────────────────────────────────────────────────────────────────
# Data Provider (kRPC streams + cached state) - VERSIÓN COMPLETA
# ──────────────────────────────────────────────────────────────────────────────

class CommandCenterDataProvider:
    def __init__(self, conn) -> None:
        self.conn = conn
        self._space_center = conn.space_center
        self._vessel = None
        self._vessel_name = None
        self._control = None
        self._auto_pilot = None
        self._flight = None
        self._orbit = None

        self.s_altitude = None
        self.s_velocity = None
        self.s_pitch = None
        self.s_heading = None
        self.s_roll = None
        self.s_g_force = None
        self.s_apoapsis = None
        self.s_periapsis = None
        self.s_inclination = None
        self.s_eccentricity = None
        self.s_period = None
        self.s_time_to_apoapsis = None
        self.s_time_to_periapsis = None
        self.s_orbital_speed = None
        self.s_semi_major_axis = None
        self.s_mass = None
        self.s_thrust = None
        self.s_available_thrust = None
        self.s_max_thrust = None
        self.s_situation = None
        self.s_sas = None
        self.s_rcs = None
        self.s_lights = None
        self.s_gear = None
        self.s_brakes = None
        self.s_throttle = None
        self.s_sas_mode = None
        self.s_target = None
        self._resource_streams: dict[str, Any] = {}
        self._engine_streams: list[dict] = []
        self._solar_panel_parts = []
        self._radiator_parts = []
        self._sas_available_modes: set = set()

        self._cache: dict[str, Any] = {}
        self._old_cache: dict[str, Any] = {}
        self._changed = False
        self.last_error: str | None = None
        self.vessel_name = "—"
        self._streams_initialized = False
        
        self._video_thread: VideoStreamThread | None = None
        self._video_frame: QPixmap | None = None
        self._frame_mutex = QMutex()
        self._base_url = "http://localhost:8080"
        self._selected_cameras: list[dict] = []

        # Iniciar servidor de telemetría la primera vez
        ensure_telemetry_server()

        self._ensure_active_vessel()

    def _ensure_active_vessel(self) -> bool:
        """Verifica si la nave activa cambió y reinicializa streams si es necesario."""
        try:
            active = self._space_center.active_vessel
            if active is None:
                return False
                
            try:
                current_name = str(active.name)
            except Exception:
                current_name = "Unknown"
            
            if self._streams_initialized and self._vessel_name == current_name:
                return False

            print(f"[CentroMando] {'Nueva nave detectada' if self._streams_initialized else 'Inicializando'}: {current_name}")
            
            self._vessel = active
            self._vessel_name = current_name
            
            self._control = active.control
            self._auto_pilot = active.auto_pilot
            self._flight = active.flight()
            self._orbit = active.orbit
            
            self._cleanup_streams()
            self._init_all_streams()
            self._streams_initialized = True
            
            try:
                self.vessel_name = current_name
            except Exception:
                self.vessel_name = "—"
                
            return True
            
        except Exception as e:
            print(f"[CentroMando] Error en _ensure_active_vessel: {e}")
            self._vessel = None
            self._vessel_name = None
            self._control = None
            self._auto_pilot = None
            self._flight = None
            self._orbit = None
            self._streams_initialized = False
            self.vessel_name = "—"
            return False

    def _cleanup_streams(self) -> None:
        """Limpia los streams existentes para evitar fugas."""
        streams = [
            self.s_altitude, self.s_velocity, self.s_pitch, self.s_heading,
            self.s_roll, self.s_g_force, self.s_apoapsis, self.s_periapsis,
            self.s_inclination, self.s_eccentricity, self.s_period,
            self.s_time_to_apoapsis, self.s_time_to_periapsis,
            self.s_orbital_speed, self.s_semi_major_axis, self.s_mass,
            self.s_thrust, self.s_available_thrust, self.s_max_thrust,
            self.s_situation, self.s_sas, self.s_rcs, self.s_lights,
            self.s_gear, self.s_brakes, self.s_throttle, self.s_sas_mode,
            self.s_target
        ]
        
        for stream in streams:
            if stream is not None:
                try:
                    self.conn.remove_stream(stream)
                except Exception:
                    pass
        
        for res_streams in self._resource_streams.values():
            for stream in res_streams.values():
                if stream is not None:
                    try:
                        self.conn.remove_stream(stream)
                    except Exception:
                        pass
        self._resource_streams.clear()
        
        for es in self._engine_streams:
            for key, stream in es.items():
                if stream is not None and key != 'part':
                    try:
                        self.conn.remove_stream(stream)
                    except Exception:
                        pass
        self._engine_streams.clear()
        
        self.s_altitude = None
        self.s_velocity = None
        self.s_pitch = None
        self.s_heading = None
        self.s_roll = None
        self.s_g_force = None
        self.s_apoapsis = None
        self.s_periapsis = None
        self.s_inclination = None
        self.s_eccentricity = None
        self.s_period = None
        self.s_time_to_apoapsis = None
        self.s_time_to_periapsis = None
        self.s_orbital_speed = None
        self.s_semi_major_axis = None
        self.s_mass = None
        self.s_thrust = None
        self.s_available_thrust = None
        self.s_max_thrust = None
        self.s_situation = None
        self.s_sas = None
        self.s_rcs = None
        self.s_lights = None
        self.s_gear = None
        self.s_brakes = None
        self.s_throttle = None
        self.s_sas_mode = None
        self.s_target = None

    def _init_all_streams(self) -> None:
        """Inicializa todos los streams de kRPC."""
        conn = self.conn
        vessel = self._vessel
        if vessel is None:
            return

        def _stream(obj, attr_name):
            try:
                return conn.add_stream(getattr, obj, attr_name)
            except Exception as e:
                print(f"[CentroMando] Error creando stream para {attr_name}: {e}")
                return None

        print("[CentroMando] Iniciando la creación de streams...")
        try:
            self.s_altitude = _stream(self._flight, "mean_altitude")
            self.s_velocity = _stream(self._flight, "velocity")
            self.s_pitch = _stream(self._flight, "pitch")
            self.s_heading = _stream(self._flight, "heading")
            self.s_roll = _stream(self._flight, "roll")
            self.s_g_force = _stream(self._flight, "g_force")

            self.s_apoapsis = _stream(self._orbit, "apoapsis_altitude")
            self.s_periapsis = _stream(self._orbit, "periapsis_altitude")
            self.s_inclination = _stream(self._orbit, "inclination")
            self.s_eccentricity = _stream(self._orbit, "eccentricity")
            self.s_period = _stream(self._orbit, "period")
            self.s_time_to_apoapsis = _stream(self._orbit, "time_to_apoapsis")
            self.s_time_to_periapsis = _stream(self._orbit, "time_to_periapsis")
            self.s_orbital_speed = _stream(self._orbit, "speed")
            self.s_semi_major_axis = _stream(self._orbit, "semi_major_axis")

            self.s_mass = _stream(vessel, "mass")
            self.s_thrust = _stream(vessel, "thrust")
            self.s_available_thrust = _stream(vessel, "available_thrust")
            self.s_max_thrust = _stream(vessel, "max_thrust")
            self.s_situation = _stream(vessel, "situation")

            self.s_sas = _stream(self._control, "sas")
            self.s_rcs = _stream(self._control, "rcs")
            self.s_lights = _stream(self._control, "lights")
            self.s_gear = _stream(self._control, "gear")
            self.s_brakes = _stream(self._control, "brakes")
            self.s_throttle = _stream(self._control, "throttle")
            
            try:
                self.s_sas_mode = conn.add_stream(getattr, self._control, "sas_mode")
            except Exception:
                self.s_sas_mode = _stream(self._auto_pilot, "sas_mode")

            self._resource_streams = {}
            resources = vessel.resources
            for res_name in RESOURCE_NAMES:
                try:
                    if res_name in resources.names:
                        self._resource_streams[res_name] = {
                            "amount": conn.add_stream(resources.amount, res_name),
                            "max": conn.add_stream(resources.max, res_name),
                        }
                except Exception as e:
                    print(f"[CentroMando] Error en recurso {res_name}: {e}")

            self._init_engine_streams()
            self.s_target = _stream(self._space_center, "target_vessel")
            self._init_part_streams()
            self._refresh_sas_available()
            
            print("[CentroMando] ¡Todos los streams cargados!")
            
        except Exception as e:
            print(f"[CentroMando] Error crítico en _init_all_streams: {e}")

    def _init_engine_streams(self) -> None:
        try:
            self._engine_parts = self._vessel.parts.engines
            self._engine_streams = []
            for eng in self._engine_parts:
                self._engine_streams.append({
                    "part": eng,
                    "active": self.conn.add_stream(getattr, eng, "active"),
                    "thrust": self.conn.add_stream(getattr, eng, "thrust"),
                    "max_thrust": self.conn.add_stream(getattr, eng, "max_thrust"),
                })
        except Exception as e:
            print(f"[CentroMando] Error en _init_engine_streams: {e}")
            self._engine_parts = []

    def _init_part_streams(self) -> None:
        try:
            self._solar_panel_parts = list(self._vessel.parts.solar_panels)
        except Exception:
            self._solar_panel_parts = []
        try:
            self._radiator_parts = list(self._vessel.parts.radiators)
        except Exception:
            self._radiator_parts = []

    def _refresh_sas_available(self) -> None:
        try:
            modes = self._auto_pilot.available_sas_modes
            self._sas_available_modes = {
                str(m.name).replace("_", "").lower() for m in modes
            }
        except Exception:
            self._sas_available_modes = set()

    def refresh(self) -> bool:
        """Actualiza todos los datos."""
        self._ensure_active_vessel()
        
        if not self._streams_initialized:
            return False

        self._old_cache = dict(self._cache)

        try:
            self._cache["altitude"] = max(0.0, float(self.s_altitude()))
            velocity = self.s_velocity()
            self._cache["velocity"] = list(velocity) if velocity else [0, 0, 0]
            self._cache["speed"] = math.sqrt(sum(v * v for v in self._cache["velocity"]))
            self._cache["pitch"] = float(self.s_pitch())
            self._cache["heading"] = float(self.s_heading())
            self._cache["roll"] = float(self.s_roll())
            self._cache["g_force"] = float(self.s_g_force())

            self._cache["apoapsis"] = max(0.0, float(self.s_apoapsis()))
            self._cache["periapsis"] = max(0.0, float(self.s_periapsis()))
            self._cache["inclination"] = float(self.s_inclination())
            self._cache["eccentricity"] = float(self.s_eccentricity())
            self._cache["period"] = float(self.s_period())
            self._cache["time_to_ap"] = float(self.s_time_to_apoapsis())
            self._cache["time_to_pe"] = float(self.s_time_to_periapsis())
            self._cache["orbital_speed"] = float(self.s_orbital_speed())
            self._cache["sma"] = float(self.s_semi_major_axis())

            self._cache["mass"] = float(self.s_mass())
            self._cache["thrust"] = float(self.s_thrust())
            self._cache["available_thrust"] = float(self.s_available_thrust())
            self._cache["max_thrust"] = float(self.s_max_thrust())

            self._cache["sas"] = bool(self.s_sas())
            self._cache["rcs"] = bool(self.s_rcs())
            self._cache["lights"] = bool(self.s_lights())
            self._cache["gear"] = bool(self.s_gear())
            self._cache["brakes"] = bool(self.s_brakes())
            self._cache["throttle"] = float(self.s_throttle())
            
            mode_val = self.s_sas_mode()
            mode_name = getattr(mode_val, "name", str(mode_val))
            self._cache["sas_mode"] = str(mode_name).replace("_", "").lower()

            mass = self._cache["mass"]
            g = 9.81
            self._cache["twr"] = self._cache["thrust"] / (mass * g) if mass > 0 else 0.0

            for res_name, streams in self._resource_streams.items():
                try:
                    amount = float(streams["amount"]())
                    maximum = float(streams["max"]())
                    self._cache[f"res_{res_name}"] = (amount, maximum)
                except Exception:
                    self._cache[f"res_{res_name}"] = (0.0, 0.0)

            engine_data = []
            for es in self._engine_streams:
                try:
                    active = bool(es["active"]())
                    thrust = float(es["thrust"]())
                    max_thrust = float(es["max_thrust"]())
                    engine_data.append({
                        "active": active,
                        "thrust": thrust,
                        "max_thrust": max_thrust,
                        "name": str(es["part"].name or "Engine"),
                    })
                except Exception:
                    pass
            self._cache["engines"] = engine_data

            try:
                target = self.s_target()
                if target:
                    try:
                        t_pos = target.position(self._vessel.orbit.body.reference_frame)
                        dist = math.sqrt(sum(v * v for v in t_pos)) if t_pos else 0.0
                        self._cache["target"] = {
                            "name": str(target.name),
                            "distance": dist,
                        }
                    except Exception:
                        self._cache.pop("target", None)
                else:
                    self._cache.pop("target", None)
            except Exception:
                self._cache.pop("target", None)

            self._cache["solar_panels"] = self._any_part_active(self._solar_panel_parts)
            self._cache["radiators"] = self._any_part_active(self._radiator_parts)

            self._refresh_sas_available()

            # Actualizar datos de telemetría para el servidor HTTP
            update_telemetry_data(self)

        except Exception as e:
            print(f"[CentroMando] Error en refresh: {e}")
            self.last_error = str(e)
            return False

        self._changed = self._cache != self._old_cache
        return self._changed

    def _any_part_active(self, parts: list) -> bool:
        """Verifica si alguna parte está activa."""
        if not parts:
            return False
        try:
            return any(getattr(p, "deployed", False) for p in parts)
        except Exception:
            return False

    def get(self, key: str, default=None):
        """Obtiene un valor del caché."""
        return self._cache.get(key, default)

    def get_resource(self, name: str) -> tuple[float, float]:
        """Obtiene la cantidad y máximo de un recurso."""
        return self._cache.get(f"res_{name}", (0.0, 0.0))

    def is_sas_mode_available(self, mode_name: str) -> bool:
        """Verifica si un modo SAS está disponible."""
        normalized = mode_name.replace("_", "").lower()
        return normalized in self._sas_available_modes

    def _run_action(self, action) -> bool:
        """Ejecuta una acción y maneja errores."""
        try:
            action()
            self.last_error = None
            return True
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def set_sas(self, enabled: bool) -> None:
        self._run_action(lambda: setattr(self._control, "sas", enabled))

    def set_rcs(self, enabled: bool) -> None:
        self._run_action(lambda: setattr(self._control, "rcs", enabled))

    def set_lights(self, enabled: bool) -> None:
        self._run_action(lambda: setattr(self._control, "lights", enabled))

    def set_gear(self, enabled: bool) -> None:
        self._run_action(lambda: setattr(self._control, "gear", enabled))

    def set_brakes(self, enabled: bool) -> None:
        self._run_action(lambda: setattr(self._control, "brakes", enabled))

    def set_throttle(self, value: float) -> None:
        clamped = max(0.0, min(1.0, value))
        self._run_action(lambda: setattr(self._control, "throttle", clamped))

    def set_sas_mode(self, mode_name: str) -> None:
        def _apply():
            target = mode_name.replace("_", "").lower()
            mode_enum = self._auto_pilot.sas_mode.__class__
            for name, val in mode_enum.__members__.items():
                if name.replace("_", "").lower() == target:
                    self._auto_pilot.sas_mode = val
                    return
            raise ValueError(f"Modo SAS '{mode_name}' no encontrado")

        self._run_action(_apply)

    def toggle_solar_panels(self) -> None:
        def _apply():
            for p in self._solar_panel_parts:
                p.deployed = not p.deployed
        self._run_action(_apply)

    def toggle_radiators(self) -> None:
        def _apply():
            for p in self._radiator_parts:
                p.deployed = not p.deployed
        self._run_action(_apply)

    # ──────────────────────────────────────────────────────────────────────────
    # Métodos para el sistema de video
    # ──────────────────────────────────────────────────────────────────────────

    def get_video_frame(self) -> QPixmap | None:
        self._frame_mutex.lock()
        frame = self._video_frame
        self._frame_mutex.unlock()
        return frame
        
    def set_video_frame(self, pixmap: QPixmap) -> None:
        self._frame_mutex.lock()
        self._video_frame = pixmap
        self._frame_mutex.unlock()
        
    def start_video_stream(self, cameras: list[dict] = None) -> None:
        if self._video_thread is not None:
            self._video_thread.stop()
            self._video_thread = None
            
        self._video_thread = VideoStreamThread(self.conn)
        self._video_thread.set_base_url(self._base_url)
        self._video_thread.frame_received.connect(self._on_video_frame)
        self._video_thread.status_changed.connect(self._on_video_status)
        self._video_thread.streams_discovered.connect(self._on_streams_discovered)
        
        if cameras is not None:
            self._selected_cameras = cameras
            self._video_thread.set_selected_cameras(cameras)
        
        self._video_thread.start()
        print("[CentroMando] VideoStreamThread iniciado")
        
    def stop_video_stream(self) -> None:
        if self._video_thread is not None:
            self._video_thread.stop()
            self._video_thread = None
            
    def get_video_stream_names(self) -> list[str]:
        if self._video_thread is not None:
            return self._video_thread.get_stream_names()
        return []
        
    def set_video_stream_by_name(self, name: str) -> bool:
        if self._video_thread is not None:
            return self._video_thread.set_active_stream_by_name(name)
        return False
        
    def set_selected_cameras(self, cameras: list[dict]) -> None:
        self._selected_cameras = cameras
        if self._video_thread is not None:
            self._video_thread.set_selected_cameras(cameras)
        
    def _on_video_frame(self, pixmap: QPixmap) -> None:
        self.set_video_frame(pixmap)
        
    def _on_video_status(self, status: str) -> None:
        print(f"[CentroMando] Video status: {status}")
        
    def _on_streams_discovered(self, stream_names: list[str]) -> None:
        print(f"[CentroMando] Streams descubiertos: {stream_names}")
        
    def is_video_streaming(self) -> bool:
        return self._video_thread is not None and self._video_thread.isRunning()


# ──────────────────────────────────────────────────────────────────────────────
# Utility functions
# ──────────────────────────────────────────────────────────────────────────────

def _format_altitude(meters: float, use_km: bool = False) -> str:
    if use_km or meters >= 10000:
        return f"{meters / 1000:.2f} km"
    return f"{meters:.0f} m"


def _format_speed(mps: float, use_kmh: bool = False) -> str:
    if use_kmh:
        return f"{mps * 3.6:.0f} km/h"
    return f"{mps:.0f} m/s"


def _format_time(seconds: float) -> str:
    if seconds <= 0 or not math.isfinite(seconds):
        return "—"
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    if m > 0:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _format_big_number(value: float, decimals: int = 1) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.{decimals}f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.{decimals}f}K"
    return f"{value:.{decimals}f}"


def _make_styled_button(text: str, active_color: str = "#1d6f91",
                        inactive_color: str = "#2a3a4a") -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedHeight(32)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {inactive_color};
            color: #dce9f6;
            border: 1px solid rgba(126, 164, 196, 80);
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: 700;
            font-family: {FONT_LABEL};
        }}
        QPushButton:hover {{
            background: #1d6f91;
            border-color: #6fc4e9;
        }}
        QPushButton:checked {{
            background: {active_color};
            border-color: #6fc4e9;
        }}
        QPushButton:disabled {{
            background: #1a2838;
            color: #5a6a7a;
            border-color: rgba(80, 100, 120, 50);
        }}
    """)
    btn.setCheckable(True)
    return btn


# ──────────────────────────────────────────────────────────────────────────────
# Widget Camera Feed
# ──────────────────────────────────────────────────────────────────────────────

class CameraFeedWidget(QWidget):
    def __init__(self, name: str, is_preview: bool = False, parent=None):
        super().__init__(parent)
        self.name = name
        self.is_preview = is_preview
        self.is_selected_preview = False
        self._video_frame: QPixmap | None = None
        self._show_placeholder = True
        self._frame_counter = 0
        self._status_text = "Esperando feed..."
        self._has_frame = False

        if is_preview:
            self.setMinimumSize(120, 80)
            self.setFixedSize(140, 90)
        else:
            self.setMinimumSize(300, 200)
            
        self.setStyleSheet("""
            QWidget {
                background-color: #050b14;
                border: 1px solid rgba(80, 120, 160, 40);
                border-radius: 4px;
            }
        """)

    def set_video_frame(self, pixmap: QPixmap | None) -> None:
        if pixmap is not None and not pixmap.isNull():
            self._video_frame = pixmap
            self._show_placeholder = False
            self._has_frame = True
            self._status_text = ""
        else:
            self._has_frame = False
        self.update()

    def set_status(self, text: str) -> None:
        self._status_text = text
        if text:
            self._show_placeholder = True
        self.update()

    def set_darkened(self, darkened: bool) -> None:
        self.is_selected_preview = darkened
        self.update()

    def update_frame(self) -> None:
        self._frame_counter += 1
        if self._show_placeholder or not self._has_frame:
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, QColor("#050b14"))

        if self._has_frame and self._video_frame is not None:
            scaled = self._video_frame.scaled(
                w, h, 
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            x = (w - scaled.width()) // 2
            y = (h - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            
            painter.setPen(QColor(0, 255, 100, 180))
            painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            painter.drawText(8, h - 8, "● LIVE")
            return

        self._draw_placeholder(painter, w, h)

        painter.setPen(QColor(111, 196, 233, 80))
        painter.drawLine(10, 10, 30, 10)
        painter.drawLine(10, 10, 10, 30)
        painter.drawLine(w - 10, h - 10, w - 30, h - 10)
        painter.drawLine(w - 10, h - 10, w - 10, h - 30)

        painter.setPen(QColor("#dce9f6"))
        font_size = 8 if self.is_preview else 12
        painter.setFont(QFont("Consolas", font_size, QFont.Weight.Bold))
        painter.drawText(15, h - 15, self.name)

        if self._status_text:
            painter.setPen(QColor("#ffaa44"))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(8, 20, self._status_text)

        if self.is_preview and self.is_selected_preview:
            painter.fillRect(0, 0, w, h, QColor(0, 0, 0, 180))
            painter.setPen(COLOR_ACCENT)
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "▲ ACTIVA")

    def _draw_placeholder(self, painter: QPainter, w: int, h: int) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#1a4a6e")))
        offset = (self._frame_counter * 2) % (w + 100)
        painter.drawEllipse(offset - 50, h // 2 - 30, 60, 60)

        painter.setBrush(QBrush(QColor("#6fc4e9")))
        painter.setPen(QPen(QColor("#6fc4e9"), 1))
        ship_x = (w // 2) + int(math.sin(self._frame_counter * 0.05) * 30)
        ship_y = h // 2 + int(math.cos(self._frame_counter * 0.03) * 20)
        painter.drawPolygon([
            QPointF(ship_x, ship_y - 12),
            QPointF(ship_x - 8, ship_y + 6),
            QPointF(ship_x + 8, ship_y + 6),
        ])

        painter.setPen(QColor("#91a8bb"))
        painter.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "BUSCANDO FEED...")

        dots = "." * (self._frame_counter // 10 % 4)
        painter.drawText(w - 40, h - 10, dots)


# ──────────────────────────────────────────────────────────────────────────────
# Camera Carousel Window (MODIFICADO - abre directamente JRTI WebView)
# ──────────────────────────────────────────────────────────────────────────────

class CameraCarouselWindow(QMainWindow):
    def __init__(self, data_provider: CommandCenterDataProvider, parent=None):
        super().__init__(parent)
        self._dp = data_provider
        self._jrti_window: JRTIWebViewWindow | None = None
        
        # Mostrar directamente la interfaz web de JRTI
        self._open_jrti_window()
        
    def _open_jrti_window(self):
        """Abre la ventana con la interfaz web de JRTI."""
        if self._jrti_window is None:
            self._jrti_window = JRTIWebViewWindow(self)
        self._jrti_window.show()
        self._jrti_window.raise_()
        self._jrti_window.activateWindow()
        
    def closeEvent(self, event):
        """Cierra la ventana y limpia recursos."""
        if self._jrti_window is not None:
            self._jrti_window.close()
            self._jrti_window = None
        super().closeEvent(event)


# ──────────────────────────────────────────────────────────────────────────────
# Widget: Quick Controls (MODIFICADO)
# ──────────────────────────────────────────────────────────────────────────────

class QuickControlsPanel(QFrame):
    camera_requested = pyqtSignal()

    def __init__(self, data_provider: CommandCenterDataProvider | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._dp = data_provider
        self.setObjectName("quickControls")
        self._locked_buttons: set[str] = set()
        self.setStyleSheet(f"""
            QFrame#quickControls {{
                background: {COLOR_PANEL_BG.name(QColor.NameFormat.HexArgb)};
                border: 1px solid rgba(126, 164, 196, 70);
                border-radius: 10px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        self.btn_sas = _make_styled_button("SAS", "#2a8a3a")
        self.btn_rcs = _make_styled_button("RCS", "#2a6a8a")
        self.btn_lights = _make_styled_button("LUCES", "#8a7a2a")
        self.btn_gear = _make_styled_button("TREN", "#8a5a2a")
        self.btn_brakes = _make_styled_button("FRENOS", "#8a2a2a")
        self.btn_solar = _make_styled_button("☀ PANELES", "#3a6a3a")
        self.btn_rad = _make_styled_button("♨ RAD", "#6a3a3a")
        self.btn_cam = _make_styled_button("🎥 JRTI", "#1d6f91", "#1a2a3a")
        self.btn_cam.setCheckable(False)

        for btn in (self.btn_sas, self.btn_rcs, self.btn_lights,
                    self.btn_gear, self.btn_brakes, self.btn_solar, self.btn_rad, self.btn_cam):
            layout.addWidget(btn)

        layout.addStretch()

        self.btn_sas.clicked.connect(lambda: self._toggle("sas"))
        self.btn_rcs.clicked.connect(lambda: self._toggle("rcs"))
        self.btn_lights.clicked.connect(lambda: self._toggle("lights"))
        self.btn_gear.clicked.connect(lambda: self._toggle("gear"))
        self.btn_brakes.clicked.connect(lambda: self._toggle("brakes"))
        self.btn_solar.clicked.connect(lambda: self._toggle("solar"))
        self.btn_rad.clicked.connect(lambda: self._toggle("radiator"))
        self.btn_cam.clicked.connect(self.camera_requested.emit)

    def set_data_provider(self, dp: CommandCenterDataProvider) -> None:
        self._dp = dp

    def _toggle(self, what: str) -> None:
        if self._dp is None:
            return
        toggles = {
            "sas": self._dp.set_sas,
            "rcs": self._dp.set_rcs,
            "lights": self._dp.set_lights,
            "gear": self._dp.set_gear,
            "brakes": self._dp.set_brakes,
            "solar": self._dp.toggle_solar_panels,
            "radiator": self._dp.toggle_radiators,
        }
        func = toggles.get(what)
        if func:
            if what in ("solar", "radiator"):
                func()
            else:
                btn_map = {
                    "sas": self.btn_sas,
                    "rcs": self.btn_rcs,
                    "lights": self.btn_lights,
                    "gear": self.btn_gear,
                    "brakes": self.btn_brakes,
                }
                btn = btn_map.get(what)
                new_state = btn.isChecked() if btn else not self._dp.get(what, False)
                func(new_state)
                self._locked_buttons.add(what)
                QTimer.singleShot(1500, lambda w=what: self._locked_buttons.discard(w))

    def sync_from_data(self) -> None:
        if self._dp is None:
            return
        if "sas" not in self._locked_buttons:
            self.btn_sas.setChecked(self._dp.get("sas", False))
        if "rcs" not in self._locked_buttons:
            self.btn_rcs.setChecked(self._dp.get("rcs", False))
        if "lights" not in self._locked_buttons:
            self.btn_lights.setChecked(self._dp.get("lights", False))
        if "gear" not in self._locked_buttons:
            self.btn_gear.setChecked(self._dp.get("gear", False))
        if "brakes" not in self._locked_buttons:
            self.btn_brakes.setChecked(self._dp.get("brakes", False))
        self.btn_solar.setChecked(self._dp.get("solar_panels", False))
        self.btn_rad.setChecked(self._dp.get("radiators", False))


# ──────────────────────────────────────────────────────────────────────────────
# Widget: SAS Mode Selector
# ──────────────────────────────────────────────────────────────────────────────

class SASModeSelector(QFrame):
    def __init__(self, data_provider: CommandCenterDataProvider | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._dp = data_provider
        self._buttons: dict[str, QPushButton] = {}
        self.setObjectName("sasModeSelector")
        self.setStyleSheet(f"""
            QFrame#sasModeSelector {{
                background: {COLOR_PANEL_BG.name(QColor.NameFormat.HexArgb)};
                border: 1px solid rgba(126, 164, 196, 70);
                border-radius: 10px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        title = QLabel("MODO SAS")
        title.setStyleSheet(f"color: {COLOR_TEXT_MUTED.name()}; font-size: 10px; "
                            f"font-weight: 700; font-family: {FONT_LABEL};")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(3)
        for i, (label, mode_key) in enumerate(SAS_MODES):
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(26)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #1a2a3a;
                    color: #b0c8d8;
                    border: 1px solid rgba(80, 120, 160, 60);
                    border-radius: 4px;
                    padding: 2px 6px;
                    font-size: 9px;
                    font-weight: 600;
                    font-family: {FONT_LABEL};
                }}
                QPushButton:hover {{
                    background: #1d6f91;
                    border-color: #6fc4e9;
                    color: #ffffff;
                }}
                QPushButton:checked {{
                    background: #2a8a3a;
                    border-color: #4ecca3;
                    color: #ffffff;
                }}
                QPushButton:disabled {{
                    background: #121e2a;
                    color: #4a5a6a;
                    border-color: rgba(50, 70, 90, 40);
                }}
            """)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, mk=mode_key: self._activate_mode(mk))
            self._buttons[mode_key] = btn
            row, col = divmod(i, 5)
            grid.addWidget(btn, row, col)

        layout.addLayout(grid)

    def set_data_provider(self, dp: CommandCenterDataProvider) -> None:
        self._dp = dp

    def _activate_mode(self, mode_key: str) -> None:
        if self._dp is None:
            return
        self._dp.set_sas_mode(mode_key)

    def sync_from_data(self) -> None:
        if self._dp is None:
            return
        current_mode = str(self._dp.get("sas_mode", ""))
        for mode_key, btn in self._buttons.items():
            available = self._dp.is_sas_mode_available(mode_key)
            btn.setEnabled(available)
            btn.setChecked(mode_key.replace("_", "").lower() == current_mode)


# ──────────────────────────────────────────────────────────────────────────────
# Widget: Throttle Control
# ──────────────────────────────────────────────────────────────────────────────

class ThrottleControl(QFrame):
    def __init__(self, data_provider: CommandCenterDataProvider | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._dp = data_provider
        self._throttle_value = 0.0
        self._updating = False

        self.setObjectName("throttleControl")
        self.setStyleSheet(f"""
            QFrame#throttleControl {{
                background: {COLOR_PANEL_BG.name(QColor.NameFormat.HexArgb)};
                border: 1px solid rgba(126, 164, 196, 70);
                border-radius: 10px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("ACELERADOR")
        title.setStyleSheet(f"color: {COLOR_TEXT_MUTED.name()}; font-size: 10px; "
                            f"font-weight: 700; font-family: {FONT_LABEL};")
        self.percent_label = QLabel("0%")
        self.percent_label.setStyleSheet(f"color: {COLOR_ACCENT.name()}; font-size: 18px; "
                                          f"font-weight: 700; font-family: {FONT_DIGITS};")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.percent_label)
        layout.addLayout(header)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setValue(0)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #1a2a3a;
                height: 10px;
                border-radius: 5px;
            }
            QSlider::handle:horizontal {
                background: #6fc4e9;
                width: 18px;
                height: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1d6f91, stop:1 #6fc4e9);
                border-radius: 5px;
            }
        """)
        self.slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self.slider)

        self.bar_widget = _ThrottleBarWidget()
        self.bar_widget.setFixedHeight(16)
        layout.addWidget(self.bar_widget)

    def set_data_provider(self, dp: CommandCenterDataProvider) -> None:
        self._dp = dp

    def _on_slider_changed(self, value: int) -> None:
        if self._updating:
            return
        throttle = value / 1000.0
        self._throttle_value = throttle
        self.percent_label.setText(f"{throttle * 100:.0f}%")
        self.bar_widget.set_value(throttle)
        if self._dp is not None:
            self._dp.set_throttle(throttle)

    def sync_from_data(self) -> None:
        if self._dp is None:
            return
        throttle = self._dp.get("throttle", 0.0)
        self._throttle_value = throttle
        self.percent_label.setText(f"{throttle * 100:.0f}%")
        self.bar_widget.set_value(throttle)
        self._updating = True
        self.slider.setValue(int(throttle * 1000))
        self._updating = False


class _ThrottleBarWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._value = 0.0

    def set_value(self, v: float) -> None:
        self._value = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        fill_w = int(w * self._value)

        painter.fillRect(0, 0, w, h, COLOR_BAR_BG)

        if fill_w > 0:
            grad = QLinearGradient(0, 0, w, 0)
            grad.setColorAt(0.0, QColor("#1d6f91"))
            grad.setColorAt(1.0, QColor("#6fc4e9"))
            painter.fillRect(0, 0, fill_w, h, grad)

        painter.setPen(QPen(QColor(60, 100, 140, 120), 1))
        painter.drawRoundedRect(0, 0, w - 1, h - 1, 3, 3)


# ──────────────────────────────────────────────────────────────────────────────
# Widget: Flight Display
# ──────────────────────────────────────────────────────────────────────────────

class FlightDisplay(QFrame):
    def __init__(self, data_provider: CommandCenterDataProvider | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._dp = data_provider
        self._use_km = False
        self._use_kmh = False

        self.setObjectName("flightDisplay")
        self.setStyleSheet(f"""
            QFrame#flightDisplay {{
                background: {COLOR_PANEL_BG.name(QColor.NameFormat.HexArgb)};
                border: 1px solid rgba(126, 164, 196, 70);
                border-radius: 10px;
            }}
        """)
        layout = QGridLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        layout.addWidget(self._make_label("ALTITUD"), 0, 0)
        self.alt_value = self._make_value_label("0 m")
        layout.addWidget(self.alt_value, 1, 0)
        self.alt_toggle = self._make_toggle_btn("m/km")
        self.alt_toggle.clicked.connect(self._toggle_alt_unit)
        layout.addWidget(self.alt_toggle, 2, 0)

        layout.addWidget(self._make_label("VELOCIDAD"), 0, 1)
        self.spd_value = self._make_value_label("0 m/s")
        layout.addWidget(self.spd_value, 1, 1)
        self.spd_toggle = self._make_toggle_btn("m/s\nkm/h")
        self.spd_toggle.clicked.connect(self._toggle_spd_unit)
        layout.addWidget(self.spd_toggle, 2, 1)

        layout.addWidget(self._make_label("APOAPSIS"), 0, 2)
        self.apo_value = self._make_value_label("0 m")
        layout.addWidget(self.apo_value, 1, 2)
        layout.addWidget(self._make_toggle_btn(""), 2, 2)

        layout.addWidget(self._make_label("PERIAPSIS"), 0, 3)
        self.pe_value = self._make_value_label("0 m")
        layout.addWidget(self.pe_value, 1, 3)
        layout.addWidget(self._make_toggle_btn(""), 2, 3)

    def set_data_provider(self, dp: CommandCenterDataProvider) -> None:
        self._dp = dp

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED.name()}; font-size: 9px; "
                          f"font-weight: 700; font-family: {FONT_LABEL};")
        return lbl

    def _make_value_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLOR_ACCENT.name()}; font-size: 20px; "
                          f"font-weight: 700; font-family: {FONT_DIGITS};")
        return lbl

    def _make_toggle_btn(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(50, 24)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: #1a2a3a;
                color: {COLOR_TEXT_MUTED.name()};
                border: 1px solid rgba(80, 120, 160, 50);
                border-radius: 4px;
                font-size: 8px;
                font-weight: 600;
                font-family: {FONT_LABEL};
            }}
            QPushButton:hover {{
                background: #1d6f91;
                color: #ffffff;
            }}
        """)
        return btn

    def _toggle_alt_unit(self) -> None:
        self._use_km = not self._use_km

    def _toggle_spd_unit(self) -> None:
        self._use_kmh = not self._use_kmh

    def sync_from_data(self) -> None:
        if self._dp is None:
            return
        alt = self._dp.get("altitude", 0.0)
        spd = self._dp.get("speed", 0.0)
        apo = self._dp.get("apoapsis", 0.0)
        pe = self._dp.get("periapsis", 0.0)

        self.alt_value.setText(_format_altitude(alt, self._use_km))
        self.spd_value.setText(_format_speed(spd, self._use_kmh))
        self.apo_value.setText(_format_altitude(apo, True))
        self.pe_value.setText(_format_altitude(pe, True))


# ──────────────────────────────────────────────────────────────────────────────
# Widget: TWR / Thrust / Mass Display
# ──────────────────────────────────────────────────────────────────────────────

class TWRDisplay(QFrame):
    def __init__(self, data_provider: CommandCenterDataProvider | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._dp = data_provider
        self.setObjectName("twrDisplay")
        self.setStyleSheet(f"""
            QFrame#twrDisplay {{
                background: {COLOR_PANEL_BG.name(QColor.NameFormat.HexArgb)};
                border: 1px solid rgba(126, 164, 196, 70);
                border-radius: 10px;
            }}
        """)
        layout = QGridLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        layout.addWidget(self._label("TWR"), 0, 0)
        self.twr_value = self._value_label("0.00")
        layout.addWidget(self.twr_value, 1, 0)

        layout.addWidget(self._label("EMPUJE"), 0, 1)
        self.thrust_value = self._value_label("0 kN")
        layout.addWidget(self.thrust_value, 1, 1)

        layout.addWidget(self._label("EMP. MÁX"), 0, 2)
        self.max_thrust_value = self._value_label("0 kN")
        layout.addWidget(self.max_thrust_value, 1, 2)

        layout.addWidget(self._label("MASA"), 0, 3)
        self.mass_value = self._value_label("0 t")
        layout.addWidget(self.mass_value, 1, 3)

    def set_data_provider(self, dp: CommandCenterDataProvider) -> None:
        self._dp = dp

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED.name()}; font-size: 9px; "
                          f"font-weight: 700; font-family: {FONT_LABEL};")
        return lbl

    def _value_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLOR_ACCENT.name()}; font-size: 16px; "
                          f"font-weight: 700; font-family: {FONT_DIGITS};")
        return lbl

    def sync_from_data(self) -> None:
        if self._dp is None:
            return
        twr = self._dp.get("twr", 0.0)
        thrust = self._dp.get("thrust", 0.0)
        max_thrust = self._dp.get("max_thrust", 0.0)
        mass = self._dp.get("mass", 0.0)

        self.twr_value.setText(f"{twr:.2f}")
        self.thrust_value.setText(f"{thrust:.1f} kN")
        self.max_thrust_value.setText(f"{max_thrust:.1f} kN")
        self.mass_value.setText(f"{mass:.1f} t")


# ──────────────────────────────────────────────────────────────────────────────
# Widget: Delta-V Display
# ──────────────────────────────────────────────────────────────────────────────

class DeltaVDisplay(QFrame):
    def __init__(self, data_provider: CommandCenterDataProvider | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._dp = data_provider
        self.setObjectName("deltaVDisplay")
        self.setStyleSheet(f"""
            QFrame#deltaVDisplay {{
                background: {COLOR_PANEL_BG.name(QColor.NameFormat.HexArgb)};
                border: 1px solid rgba(126, 164, 196, 70);
                border-radius: 10px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(16)

        total_col = QVBoxLayout()
        total_col.addWidget(self._label("ΔV TOTAL"))
        self.total_value = self._value_label("—")
        total_col.addWidget(self.total_value)
        layout.addLayout(total_col)

        stage_col = QVBoxLayout()
        stage_col.addWidget(self._label("ΔV ETAPA"))
        self.stage_value = self._value_label("—")
        stage_col.addWidget(self.stage_value)
        layout.addLayout(stage_col)

        layout.addStretch()

    def set_data_provider(self, dp: CommandCenterDataProvider) -> None:
        self._dp = dp

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED.name()}; font-size: 9px; "
                          f"font-weight: 700; font-family: {FONT_LABEL};")
        return lbl

    def _value_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLOR_GREEN.name()}; font-size: 18px; "
                          f"font-weight: 700; font-family: {FONT_DIGITS};")
        return lbl

    def sync_from_data(self) -> None:
        if self._dp is None:
            return
        self.total_value.setText("—")
        self.stage_value.setText("—")


# ──────────────────────────────────────────────────────────────────────────────
# Widget: Resource Bars
# ──────────────────────────────────────────────────────────────────────────────

class ResourceBarGroup(QFrame):
    def __init__(self, data_provider: CommandCenterDataProvider | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._dp = data_provider
        self._bars: dict[str, _ResourceBar] = {}

        self.setObjectName("resourceBars")
        self.setStyleSheet(f"""
            QFrame#resourceBars {{
                background: {COLOR_PANEL_BG.name(QColor.NameFormat.HexArgb)};
                border: 1px solid rgba(126, 164, 196, 70);
                border-radius: 10px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        title = QLabel("RECURSOS")
        title.setStyleSheet(f"color: {COLOR_TEXT_MUTED.name()}; font-size: 10px; "
                            f"font-weight: 700; font-family: {FONT_LABEL};")
        layout.addWidget(title)

        for res_name, (label, color) in RESOURCE_NAMES.items():
            bar = _ResourceBar(label, color)
            self._bars[res_name] = bar
            layout.addWidget(bar)

    def set_data_provider(self, dp: CommandCenterDataProvider) -> None:
        self._dp = dp

    def sync_from_data(self) -> None:
        if self._dp is None:
            return
        for res_name, bar in self._bars.items():
            amount, maximum = self._dp.get_resource(res_name)
            bar.set_values(amount, maximum)


class _ResourceBar(QWidget):
    def __init__(self, label: str, color: QColor, parent: QWidget | None = None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._amount = 0.0
        self._maximum = 0.0
        self.setFixedHeight(28)

    def set_values(self, amount: float, maximum: float) -> None:
        self._amount = amount
        self._maximum = maximum
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()

        painter.setPen(COLOR_TEXT)
        font = QFont(FONT_LABEL_FAMILY, 9, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(4, 0, 80, h, Qt.AlignmentFlag.AlignVCenter, self._label)

        bar_x = 84
        bar_w = w - bar_x - 80
        bar_h = 14
        bar_y = (h - bar_h) // 2
        painter.fillRect(bar_x, bar_y, bar_w, bar_h, COLOR_BAR_BG)

        if self._maximum > 0:
            fill = int(bar_w * min(1.0, self._amount / self._maximum))
            if fill > 0:
                painter.fillRect(bar_x, bar_y, fill, bar_h, self._color)

        painter.setPen(QPen(QColor(60, 100, 140, 80), 1))
        painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 3, 3)

        pct = (self._amount / self._maximum * 100) if self._maximum > 0 else 0.0
        text = f"{self._amount:.1f} / {self._maximum:.1f}  ({pct:.0f}%)"
        painter.setPen(COLOR_ACCENT)
        font2 = QFont(FONT_DIGITS_FAMILY, 9, QFont.Weight.Bold)
        painter.setFont(font2)
        painter.drawText(bar_x + bar_w + 4, 0, 76, h,
                         Qt.AlignmentFlag.AlignVCenter, text)


# ──────────────────────────────────────────────────────────────────────────────
# Widget: NavBall
# ──────────────────────────────────────────────────────────────────────────────

class NavBallWidget(QFrame):
    def __init__(self, data_provider: CommandCenterDataProvider | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._dp = data_provider
        self._size = 280
        self.setFixedSize(self._size, self._size)
        self.setObjectName("navBall")
        self.setStyleSheet(f"""
            QFrame#navBall {{
                background: {COLOR_NAVBALL_BG.name(QColor.NameFormat.HexArgb)};
                border: 2px solid rgba(80, 140, 200, 100);
                border-radius: {self._size // 2}px;
            }}
        """)

    def set_data_provider(self, dp: CommandCenterDataProvider) -> None:
        self._dp = dp

    def paintEvent(self, event) -> None:
        super().paintEvent(event)

        if self._dp is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        cx = self.width() // 2
        cy = self.height() // 2
        r = min(cx, cy) - 4

        clip_path = QPainterPath()
        clip_path.addEllipse(QPointF(cx, cy), r, r)
        painter.setClipPath(clip_path)

        pitch = self._dp.get("pitch", 0.0)
        roll = self._dp.get("roll", 0.0)
        heading = self._dp.get("heading", 0.0)

        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-roll)

        half_h = int(r * 0.7)
        sky_rect = QRectF(-r, -half_h, r * 2, half_h)
        ground_rect = QRectF(-r, 0, r * 2, half_h)

        pitch_offset = int(pitch / 90.0 * half_h)
        sky_rect.translate(0, pitch_offset)
        ground_rect.translate(0, pitch_offset)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#0a2a4a"))
        painter.drawRect(-r, -half_h, r * 2, half_h * 2)

        painter.setBrush(QColor("#0a3a6a"))
        painter.drawRect(int(sky_rect.x()), int(sky_rect.y()),
                         int(sky_rect.width()), int(sky_rect.height()))

        painter.setBrush(QColor("#3a2a1a"))
        painter.drawRect(int(ground_rect.x()), int(ground_rect.y()),
                         int(ground_rect.width()), int(ground_rect.height()))

        painter.setPen(QPen(QColor("#ffffff"), 2))
        horizon_y = pitch_offset
        painter.drawLine(-r, horizon_y, r, horizon_y)

        painter.setPen(QPen(QColor(255, 255, 255, 80), 1))
        for deg in range(-90, 91, 10):
            if deg == 0:
                continue
            y = int(deg / 90.0 * half_h + pitch_offset)
            if -half_h <= y <= half_h:
                ladder_w = 20 if deg % 20 == 0 else 10
                painter.drawLine(-ladder_w, y, ladder_w, y)

        painter.restore()

        painter.save()
        painter.translate(cx, cy)

        painter.setPen(QPen(COLOR_NAVBALL_RING, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), r - 2, r - 2)

        painter.setPen(QPen(QColor(100, 160, 220, 120), 1))
        for deg in range(0, 360, 10):
            angle_rad = math.radians(deg - 90)
            inner = r - 18 if deg % 30 == 0 else r - 12
            x1 = math.cos(angle_rad) * inner
            y1 = math.sin(angle_rad) * inner
            x2 = math.cos(angle_rad) * (r - 4)
            y2 = math.sin(angle_rad) * (r - 4)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        painter.setPen(COLOR_TEXT)
        font = QFont(FONT_LABEL_FAMILY, 9, QFont.Weight.Bold)
        painter.setFont(font)
        cardinals = [(0, "N"), (90, "E"), (180, "S"), (270, "O")]
        for deg, label in cardinals:
            angle_rad = math.radians(deg - 90)
            dist = r - 26
            x = math.cos(angle_rad) * dist
            y = math.sin(angle_rad) * dist
            painter.drawText(int(x) - 8, int(y) - 6, 16, 12,
                             Qt.AlignmentFlag.AlignCenter, label)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(COLOR_ACCENT)
        painter.drawPolygon([
            QPointF(-6, -r + 2),
            QPointF(6, -r + 2),
            QPointF(0, -r + 14),
        ])

        painter.restore()

        self._draw_marker(painter, cx, cy, r, "prograde", COLOR_GREEN)
        self._draw_marker(painter, cx, cy, r, "retrograde", COLOR_RED)
        self._draw_marker(painter, cx, cy, r, "normal", COLOR_YELLOW)
        self._draw_marker(painter, cx, cy, r, "anti_normal", COLOR_ORANGE)
        self._draw_marker(painter, cx, cy, r, "radial_in", COLOR_ACCENT)
        self._draw_marker(painter, cx, cy, r, "radial_out", QColor("#ff88aa"))

        target = self._dp.get("target")
        if target:
            self._draw_marker(painter, cx, cy, r, "target", QColor("#ff44ff"))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(COLOR_ACCENT)
        painter.drawEllipse(QPointF(cx, cy), 4, 4)

    def _draw_marker(self, painter: QPainter, cx: int, cy: int, r: int,
                     marker_type: str, color: QColor) -> None:
        if self._dp is None:
            return
        heading = self._dp.get("heading", 0.0)

        positions = {
            "prograde": (heading, 45),
            "retrograde": ((heading + 180) % 360, -45),
            "normal": ((heading + 90) % 360, 0),
            "anti_normal": ((heading + 270) % 360, 0),
            "radial_in": (heading, -20),
            "radial_out": ((heading + 180) % 360, 20),
            "target": ((heading + 30) % 360, 10),
        }
        pos = positions.get(marker_type)
        if pos is None:
            return

        m_heading, m_pitch = pos
        angle_rad = math.radians(m_heading - 90)
        pitch_rad = math.radians(m_pitch)
        dist = r * 0.6 * math.cos(pitch_rad)
        x = cx + int(dist * math.cos(angle_rad))
        y = cy + int(dist * math.sin(angle_rad))

        dx = x - cx
        dy = y - cy
        d = math.sqrt(dx * dx + dy * dy)
        if d > r - 20:
            scale = (r - 20) / d
            x = cx + int(dx * scale)
            y = cy + int(dy * scale)

        painter.setPen(QPen(color, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(x, y), 6, 6)
        painter.drawLine(x - 4, y, x + 4, y)
        painter.drawLine(x, y - 4, x, y + 4)


# ──────────────────────────────────────────────────────────────────────────────
# Widget: Orbital Info Panel
# ──────────────────────────────────────────────────────────────────────────────

class OrbitalInfoPanel(QFrame):
    def __init__(self, data_provider: CommandCenterDataProvider | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._dp = data_provider
        self.setObjectName("orbitalInfo")
        self.setStyleSheet(f"""
            QFrame#orbitalInfo {{
                background: {COLOR_PANEL_BG.name(QColor.NameFormat.HexArgb)};
                border: 1px solid rgba(126, 164, 196, 70);
                border-radius: 10px;
            }}
        """)
        layout = QGridLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        fields = [
            (0, "T. APOAPSIS", "time_ap"),
            (1, "T. PERIAPSIS", "time_pe"),
            (2, "INCLINACIÓN", "inclination"),
            (3, "EXCENTRICIDAD", "eccentricity"),
            (4, "PERÍODO", "period"),
            (5, "VEL. ORBITAL", "orbital_speed"),
        ]
        self._labels: dict[str, QLabel] = {}
        for row, label, key in fields:
            layout.addWidget(self._make_label(label), row, 0)
            val = self._make_value_label("—")
            self._labels[key] = val
            layout.addWidget(val, row, 1)

    def set_data_provider(self, dp: CommandCenterDataProvider) -> None:
        self._dp = dp

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED.name()}; font-size: 9px; "
                          f"font-weight: 700; font-family: {FONT_LABEL};")
        return lbl

    def _make_value_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLOR_ACCENT.name()}; font-size: 13px; "
                          f"font-weight: 700; font-family: {FONT_DIGITS};")
        return lbl

    def sync_from_data(self) -> None:
        if self._dp is None:
            return
        self._labels["time_ap"].setText(_format_time(self._dp.get("time_to_ap", 0.0)))
        self._labels["time_pe"].setText(_format_time(self._dp.get("time_to_pe", 0.0)))
        inc = math.degrees(self._dp.get("inclination", 0.0))
        self._labels["inclination"].setText(f"{inc:.2f}°")
        self._labels["eccentricity"].setText(f"{self._dp.get('eccentricity', 0.0):.4f}")
        self._labels["period"].setText(_format_time(self._dp.get("period", 0.0)))
        self._labels["orbital_speed"].setText(f"{self._dp.get('orbital_speed', 0.0):.0f} m/s")


# ──────────────────────────────────────────────────────────────────────────────
# Widget: Engine Status List
# ──────────────────────────────────────────────────────────────────────────────

class EngineStatusList(QFrame):
    def __init__(self, data_provider: CommandCenterDataProvider | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._dp = data_provider
        self._engine_widgets: list[QLabel] = []

        self.setObjectName("engineStatus")
        self.setStyleSheet(f"""
            QFrame#engineStatus {{
                background: {COLOR_PANEL_BG.name(QColor.NameFormat.HexArgb)};
                border: 1px solid rgba(126, 164, 196, 70);
                border-radius: 10px;
            }}
        """)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 8, 10, 8)
        self._layout.setSpacing(4)

        title = QLabel("MOTORES")
        title.setStyleSheet(f"color: {COLOR_TEXT_MUTED.name()}; font-size: 10px; "
                            f"font-weight: 700; font-family: {FONT_LABEL};")
        self._layout.addWidget(title)

        self._no_engine_label = QLabel("Sin motores")
        self._no_engine_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED.name()}; "
                                             f"font-size: 11px; font-family: {FONT_LABEL};")
        self._layout.addWidget(self._no_engine_label)

    def set_data_provider(self, dp: CommandCenterDataProvider) -> None:
        self._dp = dp

    def sync_from_data(self) -> None:
        if self._dp is None:
            return
        engines = self._dp.get("engines", [])

        for w in self._engine_widgets:
            self._layout.removeWidget(w)
            w.deleteLater()
        self._engine_widgets.clear()

        if not engines:
            self._no_engine_label.show()
            return

        self._no_engine_label.hide()
        for eng in engines:
            active = eng.get("active", False)
            name = eng.get("name", "Engine")
            thrust = eng.get("thrust", 0.0)
            max_thrust = eng.get("max_thrust", 0.0)
            status_color = COLOR_GREEN.name() if active else COLOR_RED.name()
            status_text = "ACTIVO" if active else "INACTIVO"
            text = (f"<span style='color:{status_color}; font-weight:700;'>●</span> "
                    f"<span style='color:{COLOR_TEXT.name()};'>{name}</span> "
                    f"<span style='color:{COLOR_ACCENT.name()};'>{thrust:.1f}/{max_thrust:.1f} kN</span> "
                    f"<span style='color:{status_color};'>{status_text}</span>")
            lbl = QLabel(text)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setStyleSheet("font-size: 10px; font-family: " + FONT_DIGITS + ";")
            self._layout.addWidget(lbl)
            self._engine_widgets.append(lbl)


# ──────────────────────────────────────────────────────────────────────────────
# Widget: Target Info Display
# ──────────────────────────────────────────────────────────────────────────────

class TargetInfoDisplay(QFrame):
    def __init__(self, data_provider: CommandCenterDataProvider | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._dp = data_provider
        self.setObjectName("targetInfo")
        self.setStyleSheet(f"""
            QFrame#targetInfo {{
                background: {COLOR_PANEL_BG.name(QColor.NameFormat.HexArgb)};
                border: 1px solid rgba(126, 164, 196, 70);
                border-radius: 10px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        title = QLabel("OBJETIVO")
        title.setStyleSheet(f"color: {COLOR_TEXT_MUTED.name()}; font-size: 10px; "
                            f"font-weight: 700; font-family: {FONT_LABEL};")
        layout.addWidget(title)

        self.name_label = QLabel("Sin objetivo")
        self.name_label.setStyleSheet(f"color: {COLOR_TEXT.name()}; font-size: 13px; "
                                       f"font-weight: 700; font-family: {FONT_LABEL};")
        layout.addWidget(self.name_label)

        self.dist_label = QLabel("")
        self.dist_label.setStyleSheet(f"color: {COLOR_ACCENT.name()}; font-size: 11px; "
                                       f"font-family: {FONT_DIGITS};")
        layout.addWidget(self.dist_label)

    def set_data_provider(self, dp: CommandCenterDataProvider) -> None:
        self._dp = dp

    def sync_from_data(self) -> None:
        if self._dp is None:
            return
        target = self._dp.get("target")
        if target:
            self.name_label.setText(f"🎯 {target['name']}")
            dist = target.get("distance", 0.0)
            self.dist_label.setText(f"Distancia: {_format_altitude(dist, True)}")
        else:
            self.name_label.setText("Sin objetivo")
            self.dist_label.setText("")


# ──────────────────────────────────────────────────────────────────────────────
# Widget: Alert Overlay
# ──────────────────────────────────────────────────────────────────────────────

class AlertOverlay(QFrame):
    def __init__(self, data_provider: CommandCenterDataProvider | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._dp = data_provider
        self._alerts: list[str] = []

        self.setObjectName("alertOverlay")
        self.setStyleSheet(f"""
            QFrame#alertOverlay {{
                background: transparent;
                border: none;
            }}
        """)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

    def set_data_provider(self, dp: CommandCenterDataProvider) -> None:
        self._dp = dp

    def sync_from_data(self) -> None:
        if self._dp is None:
            return
        self._alerts.clear()

        ec_amount, ec_max = self._dp.get_resource("ElectricCharge")
        if ec_max > 0 and (ec_amount / ec_max) < 0.15:
            self._alerts.append(("⚠ CARGA BAJA", COLOR_ORANGE))

        lf_amount, lf_max = self._dp.get_resource("LiquidFuel")
        ox_amount, ox_max = self._dp.get_resource("Oxidizer")
        if lf_max > 0 and lf_amount < 0.01:
            self._alerts.append(("⚠ SIN COMBUSTIBLE LF", COLOR_RED))
        if ox_max > 0 and ox_amount < 0.01:
            self._alerts.append(("⚠ SIN OXIDANTE", COLOR_RED))

        twr = self._dp.get("twr", 0.0)
        if 0 < twr < 0.5:
            self._alerts.append(("⚠ TWR INSUFICIENTE", COLOR_ORANGE))

        mp_amount, mp_max = self._dp.get_resource("Monopropellant")
        if self._dp.get("rcs", False) and mp_max > 0 and mp_amount < 0.01:
            self._alerts.append(("⚠ RCS SIN MONOPROP", COLOR_ORANGE))

        if not self._dp.get("sas", False):
            self._alerts.append(("⚠ SAS DESACTIVADO", COLOR_YELLOW))

        throttle = self._dp.get("throttle", 0.0)
        thrust = self._dp.get("thrust", 0.0)
        if throttle > 0.05 and thrust < 0.1:
            self._alerts.append(("⚠ MOTORES APAGADOS", COLOR_RED))

        self._rebuild()

    def _rebuild(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        for text, color in self._alerts:
            lbl = QLabel(text)
            lbl.setStyleSheet(f"""
                QLabel {{
                    color: {color.name()};
                    background: rgba(0, 0, 0, 180);
                    border: 1px solid {color.name()};
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 11px;
                    font-weight: 700;
                    font-family: {FONT_DIGITS};
                }}
            """)
            self._layout.addWidget(lbl)


# ──────────────────────────────────────────────────────────────────────────────
# Main Screen: CentroMandoScreen (MODIFICADO)
# ──────────────────────────────────────────────────────────────────────────────

class CentroMandoScreen(QWidget):
    back_clicked = pyqtSignal()

    def __init__(self, conn=None, parent: QWidget | None = None):
        super().__init__(parent)
        self._conn = conn
        self._dp: CommandCenterDataProvider | None = None
        self._connected = False
        self._camera_window: CameraCarouselWindow | None = None

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update)
        self._timer.setInterval(33)

        if conn is not None:
            self.set_connection(conn)

    def set_connection(self, conn) -> None:
        self._conn = conn
        if conn is None:
            self._connected = False
            self._dp = None
            self._vessel_label.setText("")
            self._timer.stop()
            return

        try:
            self._dp = CommandCenterDataProvider(conn)
            self._connected = True
            self._vessel_label.setText(f"Nave: {self._dp.vessel_name}")
            for widget in self._find_data_widgets():
                widget.set_data_provider(self._dp)
            if not self._timer.isActive():
                self._timer.start()
        except Exception as exc:
            self._connected = False
            self._dp = None
            self._timer.stop()
            self._status_label.setText(f"Error kRPC: {exc}")

    def _find_data_widgets(self) -> list:
        found = []
        stack = [self]
        while stack:
            w = stack.pop()
            if hasattr(w, "set_data_provider") and w is not self:
                found.append(w)
            for child in w.findChildren(QWidget, options=Qt.FindChildOption.FindChildrenRecursively):
                if hasattr(child, "set_data_provider") and child not in found:
                    found.append(child)
        return found

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._connected and self._dp is not None and not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if self._timer.isActive():
            self._timer.stop()
        if self._dp is not None:
            self._dp.stop_video_stream()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(12)

        title = QLabel("CENTRO DE MANDO")
        title.setStyleSheet("color: #f3f8fc; font-size: 20px; font-weight: 700; "
                            f"font-family: {FONT_LABEL};")
        header.addWidget(title)

        self._status_label = QLabel("Conectando...")
        self._status_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED.name()}; "
                                          f"font-size: 11px; font-family: {FONT_LABEL};")
        header.addWidget(self._status_label)

        self._vessel_label = QLabel("")
        self._vessel_label.setStyleSheet(f"color: {COLOR_ACCENT.name()}; "
                                          f"font-size: 11px; font-weight: 700; "
                                          f"font-family: {FONT_LABEL};")
        header.addWidget(self._vessel_label)

        header.addStretch()

        back_btn = QPushButton("← Volver")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet("""
            QPushButton {
                background: #1d6f91;
                color: #f3fbff;
                border: 1px solid #66c7e8;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 700;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #2585aa;
                border-color: #9ee4f5;
            }
        """)
        back_btn.clicked.connect(self.back_clicked.emit)
        header.addWidget(back_btn)

        root.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        self._quick_controls = QuickControlsPanel()
        self._quick_controls.camera_requested.connect(self._open_jrti_window)
        content_layout.addWidget(self._quick_controls)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self._sas_selector = SASModeSelector()
        row2.addWidget(self._sas_selector, 2)
        self._throttle = ThrottleControl()
        row2.addWidget(self._throttle, 1)
        content_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(8)
        self._flight_display = FlightDisplay()
        row3.addWidget(self._flight_display, 2)

        navball_container = QVBoxLayout()
        navball_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._navball = NavBallWidget()
        navball_container.addWidget(self._navball)
        row3.addLayout(navball_container, 1)
        content_layout.addLayout(row3)

        row4 = QHBoxLayout()
        row4.setSpacing(8)
        self._twr_display = TWRDisplay()
        row4.addWidget(self._twr_display, 1)
        self._delta_v = DeltaVDisplay()
        row4.addWidget(self._delta_v, 1)
        self._resources = ResourceBarGroup()
        row4.addWidget(self._resources, 2)
        content_layout.addLayout(row4)

        row5 = QHBoxLayout()
        row5.setSpacing(8)
        self._orbital_info = OrbitalInfoPanel()
        row5.addWidget(self._orbital_info, 1)
        self._engine_status = EngineStatusList()
        row5.addWidget(self._engine_status, 1)
        content_layout.addLayout(row5)

        self._target_info = TargetInfoDisplay()
        content_layout.addWidget(self._target_info)

        content_layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self._alert_overlay = AlertOverlay(parent=self)
        self._alert_overlay.setGeometry(self.width() - 300, self.height() - 200, 280, 180)

        fade_in(self, 180)

    def _open_jrti_window(self):
        """Abre la ventana con la interfaz web de JRTI."""
        if self._camera_window is not None:
            try:
                self._camera_window.close()
                self._camera_window = None
            except Exception:
                pass

        self._camera_window = CameraCarouselWindow(data_provider=self._dp, parent=self)
        self._camera_window.setWindowFlags(Qt.WindowType.Window)
        self._camera_window.show()
        self._camera_window.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_alert_overlay"):
            self._alert_overlay.setGeometry(
                self.width() - 300, self.height() - 220, 280, 200
            )
            self._alert_overlay.raise_()

    def _update(self) -> None:
        if not self._connected or self._dp is None:
            self._status_label.setText("Desconectado")
            return

        try:
            self._dp.refresh()
        except Exception as exc:
            print(f"[CentroMando] Error crítico en _update loop: {exc}")
            self._connected = False
            self._status_label.setText(f"Error: {exc}")
            self._timer.stop()
            return

        if self._dp.last_error:
            self._status_label.setText(f"⚠ Comando falló: {self._dp.last_error}")
        else:
            self._status_label.setText("Conectado ✓")
        
        self._vessel_label.setText(f"Nave: {self._dp.vessel_name}")

        if not self._dp._streams_initialized:
            return

        try:
            self._quick_controls.sync_from_data()
            self._sas_selector.sync_from_data()
            self._throttle.sync_from_data()
            self._flight_display.sync_from_data()
            self._twr_display.sync_from_data()
            self._delta_v.sync_from_data()
            self._resources.sync_from_data()
            self._orbital_info.sync_from_data()
            self._engine_status.sync_from_data()
            self._target_info.sync_from_data()
            self._alert_overlay.sync_from_data()
            
            self._navball.update()
        except Exception as e:
            print(f"[CentroMando] Error al sincronizar widgets: {e}")

    def closeEvent(self, event) -> None:
        if self._dp is not None:
            self._dp.stop_video_stream()
        if self._camera_window is not None:
            try:
                self._camera_window.close()
                self._camera_window = None
            except Exception:
                pass
        super().closeEvent(event)