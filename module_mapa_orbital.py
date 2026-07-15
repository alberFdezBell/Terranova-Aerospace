"""
Module for the Orbital Map visualizer.
Provides real-time tracking of KSP vessels if krpc is available.
"""

from __future__ import annotations

import math
import os
import time
from pathlib import Path

from PyQt6.QtCore import pyqtSignal, QTimer, Qt, QRect, QEasingCurve, QPropertyAnimation, QPointF
from PyQt6.QtGui import QMouseEvent, QWheelEvent, QPainter, QPen, QColor, QPixmap, QFont, QFontMetrics, QVector3D
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QLineEdit, QPushButton, QFrame, QScrollArea, QLayout, QMessageBox
from PyQt6.QtCore import QVariantAnimation

from core_shared import (
    BASE_DIR,
    _KSP_AVAILABLE,
    np,
    krpc,
    gl,
    ConnectThread,
    connect_to_ksp_async,
    LUNAR_BODY_NAMES,
    _is_lunar_body,
    _normalize_key,
)

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

    # Colores fijos de punto según tipo de nave
    DOT_COLOR_STATION = (0.35, 1.0, 0.0, 1.0)   # Azul  → estación espacial
    DOT_COLOR_DEBRIS  = (1.0,  0.22, 0.22, 1.0)   # Rojo  → basura espacial
    DOT_COLOR_SAT     = (1.0,  1.0,  1.0,  1.0)   # Blanco → satélite genérico

    MUN_DRAW_RADIUS = 280    # Radio visual de la Luna en el mapa (unidades km)
    MUN_COLOR       = (0.52, 0.56, 0.62, 1.0)   # Gris-azulado para la Luna
    MUN_ORBIT_COLOR = (0.35, 0.38, 0.50, 0.55)  # Órbita de la Luna (tenue)
    MUN_RADIUS_KM   = 200.0  # Radio superficial de la Luna en KSP (km)

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

    class IconsOverlay(QWidget):
        """Overlay transparente que dibuja iconos personalizados sobre las posiciones de las naves."""

        def __init__(self, view_widget, visualizer, parent=None):
            super().__init__(parent)
            self._view = view_widget
            self._visualizer = visualizer
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            for vid, obj in self._visualizer.render_objects.items():
                selected = self._visualizer.selected_vessel
                show_in_map = selected is None or selected == vid
                if not show_in_map:
                    continue

                current = self._visualizer._hover_current.get(vid, 1.0)
                if current <= 0.01:
                    continue

                proj = self._visualizer._project_vessel(vid)
                if proj is None:
                    continue

                px, py, _ = proj

                vessel_type = str(obj.get('vessel_type', '')).strip().lower()

                icon_path = None
                if 'station' in vessel_type or 'estacion' in vessel_type:
                    icon_path = self._visualizer.icon_estacion_path
                elif 'debris' in vessel_type or 'basura' in vessel_type:
                    icon_path = self._visualizer.icon_basura_path
                else:
                    icon_path = self._visualizer.icon_sat_path

                pixmap = None
                if icon_path and os.path.exists(icon_path):
                    pixmap = self._visualizer._get_cached_icon(icon_path)

                if pixmap and not pixmap.isNull():
                    current = self._visualizer._hover_current.get(vid, 1.0)
                    painter.setOpacity(current)
                    scale = getattr(self._visualizer, 'icon_scale', 1.0)
                    w = int(pixmap.width() * scale)
                    h = int(pixmap.height() * scale)
                    painter.drawPixmap(int(px - w / 2), int(py - h / 2), w, h, pixmap)

    class MapLegendWidget(QFrame):
        """Widget de leyenda flotante interactivo para filtrar satélites por grupo."""

        def __init__(self, visualizer, parent=None):
            super().__init__(parent)
            self._visualizer = visualizer

            self.setStyleSheet("""
                QFrame {
                    background: rgba(13, 17, 23, 220);
                    border: 1px solid #30363d;
                    border-radius: 8px;
                }
                QLabel {
                    border: none;
                    background: transparent;
                    color: #8b949e;
                    font-size: 10px;
                    font-weight: bold;
                }
            """)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(6)

            title = QLabel("FILTRAR GRUPOS")
            layout.addWidget(title)

            self.btn_sat = QPushButton("⚪ Satélites")
            self._setup_item_style(self.btn_sat, "#FFFFFF")
            self.btn_sat.clicked.connect(self._toggle_sat)
            layout.addWidget(self.btn_sat)

            self.btn_station = QPushButton("🔵 Estaciones")
            self._setup_item_style(self.btn_station, "#408df8")
            self.btn_station.clicked.connect(self._toggle_station)
            layout.addWidget(self.btn_station)

            self.btn_debris = QPushButton("🔴 Basura")
            self._setup_item_style(self.btn_debris, "#ff4b4b")
            self.btn_debris.clicked.connect(self._toggle_debris)
            layout.addWidget(self.btn_debris)

        def _setup_item_style(self, btn, color_hex):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    color: {color_hex};
                    font-size: 11px;
                    font-weight: bold;
                    text-align: left;
                    padding: 4px 6px;
                }}
                QPushButton:hover {{
                    background: rgba(255, 255, 255, 15);
                    border-radius: 4px;
                }}
            """)

        def _toggle_sat(self):
            self._visualizer.group_sat_enabled = not self._visualizer.group_sat_enabled
            self._update_ui_style()
            self._visualizer._update_selection_visuals()

        def _toggle_station(self):
            self._visualizer.group_station_enabled = not self._visualizer.group_station_enabled
            self._update_ui_style()
            self._visualizer._update_selection_visuals()

        def _toggle_debris(self):
            self._visualizer.group_debris_enabled = not self._visualizer.group_debris_enabled
            self._update_ui_style()
            self._visualizer._update_selection_visuals()

        def _update_ui_style(self):
            def apply_style(btn, color_hex, enabled):
                color = color_hex if enabled else "#8b949e"
                text_decor = "none" if enabled else "line-through"
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent;
                        border: none;
                        color: {color};
                        font-size: 11px;
                        font-weight: bold;
                        text-align: left;
                        padding: 4px 6px;
                        text-decoration: {text_decor};
                    }}
                    QPushButton:hover {{
                        background: rgba(255, 255, 255, 15);
                        border-radius: 4px;
                    }}
                """)
            apply_style(self.btn_sat, "#FFFFFF", self._visualizer.group_sat_enabled)
            apply_style(self.btn_station, "#408df8", self._visualizer.group_station_enabled)
            apply_style(self.btn_debris, "#ff4b4b", self._visualizer.group_debris_enabled)

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

            title = QLabel(f"{name}")
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

            # Alfa actual / objetivo por nave, usados para oscurecer de forma
            # suave y transicionada las órbitas y satélites que no están bajo
            # el cursor cuando se hace hover sobre uno de ellos.
            self._hover_current: dict = {}
            self._hover_targets: dict = {}

            self.last_mouse_pos = None
            self.is_rotating = False
            self._press_pos = None
            self._press_vessel = None

            # ── Seguimiento del cuerpo lunar ──────────────────────────────────
            self.lunar_body_name: str   = ""
            self.lunar_body_obj         = None
            self.moon_pos_3d: tuple     = (0.0, 0.0, 0.0)
            self.moon_render: dict      = {}
            self._moon_refresh_t: float = 0.0
            self.camera_target_body: str = 'kerbin'

            # ── Iconos de satélites (Rutas, escala y cache) ───────────────────
            self.icon_estacion_path = os.path.join(BASE_DIR, "icons", "sat", "estacion.png")
            self.icon_basura_path = os.path.join(BASE_DIR, "icons", "sat", "basura.png")
            self.icon_sat_path = os.path.join(BASE_DIR, "icons", "sat", "sat.png")
            self.icon_scale = 0.5  # <--- ESCALA DE ICONOS CONFIGURABLE EN EL CÓDIGO
            self._icon_cache = {}

            # Habilitación por grupo (para filtros de leyenda)
            self.group_sat_enabled = True
            self.group_station_enabled = True
            self.group_debris_enabled = True

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
            ruta_imagen = BASE_DIR / "icons" / "tas_cortado.png"
            px = QPixmap(str(ruta_imagen))
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

            self.icons_overlay = IconsOverlay(self.view, self, self.view)
            self.icons_overlay.show()

            self.legend_widget = MapLegendWidget(self, self.view)
            self.legend_widget.show()

            

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
                btn = QPushButton(f"{vid}")
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
                f"<span style='color:{color_hex}'>{vessel_name}</span>"
            )

            alt_km   = info.get('alt_km', 0)
            period   = info.get('period', 0)
            inc_rad  = info.get('inc', 0)
            ecc      = info.get('ecc', 0)
            vel_ms   = info.get('vel_ms', 0)
            body_name = info.get('body_name', '')

            c_key = "#6e7681"   # color etiqueta
            c_val = "#e6edf3"   # color valor
            body_row = (
                f"<span style='color:{c_key}'>Cuerpo</span>  "
                f"<span style='color:{c_val}'>{body_name}</span><br>"
                if body_name else ""
            )
            self.info_body.setText(
                f"{body_row}"
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
            self.camera_target_body = 'kerbin'
            self._animate_camera_to(QVector3D(0, 0, 0), 5200.0, -45.0, 22.0, duration=900)

        # ── Helpers del cuerpo lunar ───────────────────────────────────────────

        def _find_lunar_body(self):
            """Busca la Luna entre los cuerpos celestes de KSP.
            Devuelve (nombre, objeto_body) o (None, None) si no se encuentra."""
            if not self.conn:
                return None, None
            try:
                for name, body in self.conn.space_center.bodies.items():
                    if _is_lunar_body(name):
                        return name, body
            except Exception:
                pass
            return None, None

        def _setup_moon(self, moon_name: str, moon_body) -> bool:
            """Construye los GL items para la esfera de la Luna y su órbita alrededor de Kerbin."""
            try:
                orb    = moon_body.orbit
                sma    = float(orb.semi_major_axis) / 1000.0
                inc    = float(orb.inclination)
                lan    = float(orb.longitude_of_ascending_node)
                argp   = float(orb.argument_of_periapsis)
                ecc    = float(orb.eccentricity)
                period = float(orb.period)
                ta     = float(orb.true_anomaly)

                ci, si_ = np.cos(inc), np.sin(inc)
                cl, sl  = np.cos(lan), np.sin(lan)
                ca, sa  = np.cos(argp), np.sin(argp)
                R = (np.array([[cl, -sl, 0], [sl, cl, 0], [0, 0, 1]])
                     @ np.array([[1, 0, 0], [0, ci, -si_], [0, si_, ci]])
                     @ np.array([[ca, -sa, 0], [sa, ca, 0], [0, 0, 1]]))

                r_now = sma * (1 - ecc ** 2) / (1 + ecc * math.cos(ta))
                pos   = R @ np.array([r_now * math.cos(ta), r_now * math.sin(ta), 0.0])
                mx, my, mz = float(pos[0]), float(pos[1]), float(pos[2])

                # Órbita de la Luna alrededor de Kerbin
                theta_m   = np.linspace(0, 2 * np.pi, ORBIT_POINTS)
                r_t       = sma * (1 - ecc ** 2) / (1 + ecc * np.cos(theta_m))
                orbit_pts = (R @ np.vstack([
                    r_t * np.cos(theta_m),
                    r_t * np.sin(theta_m),
                    np.zeros(ORBIT_POINTS),
                ])).T.astype(np.float32)

                moon_orbit_line = gl.GLLinePlotItem(
                    pos=orbit_pts, color=MUN_ORBIT_COLOR,
                    width=1.2, antialias=True, mode='line_strip', glOptions='opaque',
                )

                # Esfera de la Luna
                md = gl.MeshData.sphere(rows=20, cols=32, radius=MUN_DRAW_RADIUS)
                moon_sphere = gl.GLMeshItem(
                    meshdata=md, smooth=True, color=MUN_COLOR,
                    drawEdges=False, drawFaces=True,
                    shader='shaded', glOptions='opaque',
                )
                moon_sphere.translate(mx, my, mz)

                self.view.addItem(moon_orbit_line)
                self.view.addItem(moon_sphere)

                self.lunar_body_name = moon_name
                self.lunar_body_obj  = moon_body
                self.moon_pos_3d     = (mx, my, mz)
                self.moon_render     = {
                    'sphere':            moon_sphere,
                    'orbit_line':        moon_orbit_line,
                    'R_matrix':          R,
                    'r_orbit':           sma,
                    'ecc':               ecc,
                    'period':            period,
                    'true_anomaly_base': ta,
                    'last_update_time':  time.time(),
                }
                return True
            except Exception:
                return False

        def _remove_moon(self) -> None:
            """Elimina los GL items de la Luna del escenario."""
            for key in ('sphere', 'orbit_line'):
                item = self.moon_render.get(key)
                if item is not None:
                    try:
                        self.view.removeItem(item)
                    except Exception:
                        pass
            self.moon_render.clear()
            self.lunar_body_name = ""
            self.lunar_body_obj  = None
            self.moon_pos_3d     = (0.0, 0.0, 0.0)

        def _refresh_moon_from_ksp(self) -> None:
            """Actualiza la anomalía verdadera de la Luna leyendo el dato real de KSP."""
            if not self.conn or not self.moon_render or self.lunar_body_obj is None:
                return
            try:
                ta = float(self.lunar_body_obj.orbit.true_anomaly)
                self.moon_render['true_anomaly_base'] = ta
                self.moon_render['last_update_time']  = time.time()
            except Exception:
                pass

        def _animate_moon(self) -> None:
            """Extrapola la posición de la Luna con mecánica Kepleriana y mueve su esfera GL."""
            mr = self.moon_render
            if not mr:
                return
            R       = mr.get('R_matrix')
            r_orbit = mr.get('r_orbit')
            ecc     = mr.get('ecc')
            period  = mr.get('period')
            ta_base = mr.get('true_anomaly_base')
            t0      = mr.get('last_update_time')
            if R is None or r_orbit is None or ecc is None or not period or ta_base is None or t0 is None:
                return
            dt = time.time() - t0
            ta = self._propagate_true_anomaly(ecc, period, ta_base, dt)
            r  = r_orbit * (1 - ecc ** 2) / (1 + ecc * math.cos(ta))
            pos = R @ np.array([r * math.cos(ta), r * math.sin(ta), 0.0])
            mx, my, mz   = float(pos[0]), float(pos[1]), float(pos[2])
            self.moon_pos_3d = (mx, my, mz)
            sphere = mr.get('sphere')
            if sphere is not None:
                sphere.resetTransform()
                sphere.translate(mx, my, mz)

        def _celestial_body_at_cursor(self, event):
            proj_kerbin = self._project_point((0.0, 0.0, 0.0))
            proj_moon = None
            if self.moon_render:
                proj_moon = self._project_point(self.moon_pos_3d)

            cursor_pos = event.position()
            best_body = None
            best_dist = 999999.0

            cam_dist = self.view.opts['distance']

            if proj_kerbin is not None:
                kx, ky, _ = proj_kerbin
                dist_k = math.hypot(cursor_pos.x() - kx, cursor_pos.y() - ky)
                rad_k_px = (PLANET_DRAW_RADIUS / cam_dist) * (self.view.height() / 2) * 1.5
                rad_k_px = max(24.0, min(rad_k_px, 200.0))
                if dist_k <= rad_k_px:
                    best_body = 'kerbin'
                    best_dist = dist_k

            if proj_moon is not None:
                mx, my, _ = proj_moon
                dist_m = math.hypot(cursor_pos.x() - mx, cursor_pos.y() - my)
                rad_m_px = (MUN_DRAW_RADIUS / cam_dist) * (self.view.height() / 2) * 1.5
                rad_m_px = max(18.0, min(rad_m_px, 150.0))
                if dist_m <= rad_m_px:
                    if dist_m < best_dist:
                        best_body = 'moon'
                        best_dist = dist_m

            return best_body

        def _focus_body(self, body: str):
            if body == 'moon' and self.moon_render:
                self.camera_target_body = 'moon'
                mx, my, mz = self.moon_pos_3d
                pos = QVector3D(mx, my, mz)
                self._animate_camera_to(pos, self.view.opts['distance'], self.view.opts['azimuth'], self.view.opts['elevation'], duration=700)
            else:
                self.camera_target_body = 'kerbin'
                pos = QVector3D(0, 0, 0)
                self._animate_camera_to(pos, self.view.opts['distance'], self.view.opts['azimuth'], self.view.opts['elevation'], duration=700)

        @staticmethod
        def _dot_color_for_type(vessel_type: str) -> tuple:
            """Devuelve el color RGBA del punto del satélite según su tipo de nave KSP."""
            vt = str(vessel_type or '').strip().lower()
            if 'station' in vt:
                return DOT_COLOR_STATION    # Azul  → estación espacial
            if 'debris' in vt:
                return DOT_COLOR_DEBRIS     # Rojo  → basura espacial
            return DOT_COLOR_SAT            # Blanco → cualquier otro

        def _get_cached_icon(self, path: str) -> QPixmap:
            if path not in self._icon_cache:
                self._icon_cache[path] = QPixmap(path)
            return self._icon_cache[path]

        def _has_icon_for_vessel(self, vessel_type: str) -> bool:
            v_type = str(vessel_type or '').strip().lower()
            if 'station' in v_type or 'estacion' in v_type:
                path = self.icon_estacion_path
            elif 'debris' in v_type or 'basura' in v_type:
                path = self.icon_basura_path
            else:
                path = self.icon_sat_path
            return bool(path and os.path.exists(path))

        def _is_vessel_group_enabled(self, vessel_type: str) -> bool:
            vt = str(vessel_type or '').strip().lower()
            if 'station' in vt:
                return self.group_station_enabled
            if 'debris' in vt:
                return self.group_debris_enabled
            return self.group_sat_enabled

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
            phi   = rng.uniform(0, 2 * np.pi, 1500)
            theta = np.arccos(rng.uniform(-1, 1, 1500))
            dist  = rng.uniform(75000, 95000, 1500)
            stars = np.column_stack([
                dist * np.sin(theta) * np.cos(phi),
                dist * np.sin(theta) * np.sin(phi),
                dist * np.cos(theta)
            ]).astype(np.float32)
            star_sizes = rng.uniform(1.0, 2.5, 1500).astype(np.float32)
            star_colors = np.ones((1500, 4), dtype=np.float32)
            star_colors[:, 3] = rng.uniform(0.3, 0.9, 1500).astype(np.float32)
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
            # Detectar y renderizar el cuerpo lunar del sistema solar activo
            moon_n, moon_b = self._find_lunar_body()
            if moon_n and not self.moon_render:
                self._setup_moon(moon_n, moon_b)
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
            self._hover_current.clear()
            self._hover_targets.clear()

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
            # Eliminar luna
            self._remove_moon()

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

                vessel_type = str(obj.get('vessel_type', '')).strip().lower()
                group_enabled = True
                if 'station' in vessel_type:
                    group_enabled = self.group_station_enabled
                elif 'debris' in vessel_type:
                    group_enabled = self.group_debris_enabled
                else:
                    group_enabled = self.group_sat_enabled

                if not group_enabled:
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
            return f"<b style='color:{color_hex}'>{vessel_name}</b>"

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

            # Fija los nuevos objetivos de alfa para el fundido de hover; la
            # transición suave hacia esos objetivos la realiza cada frame
            # _animate_hover_alpha, en vez de aplicar el oscurecido de golpe.
            self._compute_hover_targets()

            highlighted_items = []

            for vid, obj in self.render_objects.items():
                is_selected = self.selected_vessel == vid
                is_hovered = self.hovered_vessel == vid
                group_enabled = self._is_vessel_group_enabled(obj.get('vessel_type', ''))
                show_in_map = (self.selected_vessel is None or is_selected) and group_enabled

                line = obj.get('line')
                dot = obj.get('dot')
                trail = obj.get('trail_line')

                line_width = 3.5 if (is_selected or is_hovered) else 1.5

                if line is not None:
                    line.setVisible(show_in_map)
                    if show_in_map:
                        line.setData(pos=obj['orbit_pts'], width=line_width)
                        if is_hovered or is_selected:
                            highlighted_items.append(line)

                if dot is not None:
                    has_icon = self._has_icon_for_vessel(obj.get('vessel_type', ''))
                    dot.setVisible(show_in_map and not has_icon)
                    if show_in_map and not has_icon and (is_hovered or is_selected):
                        highlighted_items.append(dot)

                if trail is not None:
                    trail.setVisible(show_in_map)
                    if show_in_map and (is_hovered or is_selected):
                        highlighted_items.append(trail)

            # PyQtGraph pinta los GL items en orden de insercion; reinsertar el destacado
            # evita que una orbita atenuada de la misma trayectoria se mezcle por encima.
            for item in highlighted_items:
                try:
                    self.view.removeItem(item)
                    self.view.addItem(item)
                except Exception:
                    pass

        def _compute_hover_targets(self):
            """Calcula, para cada nave, el alfa objetivo según el hover/selección
            actual. No aplica el color todavía: la interpolación suave hacia
            estos objetivos ocurre en _animate_hover_alpha en cada frame."""
            has_hover = self.hovered_vessel is not None and self.selected_vessel is None

            for vid, obj in self.render_objects.items():
                vessel_type = str(obj.get('vessel_type', '')).strip().lower()
                group_enabled = True
                if 'station' in vessel_type:
                    group_enabled = self.group_station_enabled
                elif 'debris' in vessel_type:
                    group_enabled = self.group_debris_enabled
                else:
                    group_enabled = self.group_sat_enabled

                if not group_enabled:
                    self._hover_targets[vid] = 0.0
                elif has_hover:
                    self._hover_targets[vid] = 1.0 if vid == self.hovered_vessel else 0.08
                else:
                    self._hover_targets[vid] = 1.0

        def _animate_hover_alpha(self):
            """Interpola el alfa actual de cada nave hacia su objetivo y aplica
            el color resultante a su órbita, punto y estela, logrando un
            oscurecido suave y transicionado en lugar de un cambio brusco."""
            if not self.render_objects:
                return

            factor = 0.15  # velocidad de la transición por frame

            for vid, obj in self.render_objects.items():
                target = self._hover_targets.get(vid, 1.0)
                current = self._hover_current.get(vid, 1.0)

                diff = target - current
                if abs(diff) < 0.001:
                    current = target
                else:
                    current += diff * factor
                    current = min(current, target) if diff > 0 else max(current, target)

                self._hover_current[vid] = current

                # Línea orbital
                line = obj.get('line')
                base_line = obj.get('base_line_color')
                if line is not None and base_line is not None:
                    line.setData(color=(base_line[0], base_line[1], base_line[2],
                                         base_line[3] * current))
                    line.setVisible(current > 0.01)

                # Punto (satélite)
                dot = obj.get('dot')
                base_dot = obj.get('base_dot_color')
                if dot is not None and base_dot is not None:
                    has_icon = self._has_icon_for_vessel(obj.get('vessel_type', ''))
                    dot.setData(color=(base_dot[0], base_dot[1], base_dot[2],
                                        base_dot[3] * current))
                    dot.setVisible(current > 0.01 and not has_icon)

                # Estela
                trail = obj.get('trail_line')
                base_trail = obj.get('base_trail_colors')
                ordered = obj.get('ordered_trail')
                if trail is not None and base_trail is not None and ordered is not None:
                    faded_trail = base_trail.copy()
                    faded_trail[:, 3] = base_trail[:, 3] * current
                    trail.setData(pos=ordered, color=faded_trail)
                    trail.setVisible(current > 0.01)

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
                        try:
                            vt_obj = getattr(vessel, 'type', None)
                            vessel_type = str(getattr(vt_obj, 'name', vt_obj) or '').strip().lower()
                        except Exception:
                            vessel_type = ''

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

                        # ── Detección del cuerpo orbitado ──────────────────────
                        try:
                            _body_name = str(getattr(vessel.orbit.body, 'name', '') or '').strip()
                        except Exception:
                            _body_name = ''
                        _is_lunar = _is_lunar_body(_body_name)
                        if _is_lunar and not self.moon_render:
                            _mn, _mb = self._find_lunar_body()
                            if _mn:
                                self._setup_moon(_mn, _mb)

                        inc = streams['inc']()
                        lan = streams['lan']()
                        argp = streams['argp']()
                        ecc = streams['ecc']()
                        period = streams['period']()
                        r_orbit = sma / 1000.0
                        # max_orbit_radius se actualiza abajo tras el offset lunar

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

                        # ── Offset lunar y altitud ─────────────────────────────
                        if _is_lunar:
                            mx, my, mz = self.moon_pos_3d
                            _off      = np.array([mx, my, mz], dtype=np.float32)
                            rotated_w = rotated + _off
                            sx_w, sy_w, sz_w = sx + mx, sy + my, sz + mz
                            _moon_r   = math.hypot(math.hypot(mx, my), mz)
                            max_orbit_radius = max(max_orbit_radius, _moon_r + r_orbit * (1.0 + ecc))
                            alt_km    = r_now - MUN_RADIUS_KM
                        else:
                            rotated_w = rotated
                            sx_w, sy_w, sz_w = sx, sy, sz
                            max_orbit_radius = max(max_orbit_radius, r_orbit * (1.0 + ecc))
                            alt_km    = r_now - KERBIN_RADIUS_KM

                        vel_ms = 0.0
                        try:
                            if streams['orbital_speed'] is not None:
                                vel_ms = streams['orbital_speed']()
                        except Exception:
                            pass

                        info_data = {
                            'alt_km':    alt_km,
                            'period':    period,
                            'inc':       inc,
                            'ecc':       ecc,
                            'vel_ms':    vel_ms,
                            'body_name': _body_name,
                            'is_lunar':  _is_lunar,
                        }

                        if vid not in self.render_objects:
                            cidx = self.color_counter % len(VESSEL_COLORS)
                            self.color_counter += 1
                            lc = VESSEL_COLORS[cidx]
                            dc = self._dot_color_for_type(vessel_type)

                            line = gl.GLLinePlotItem(
                                pos=rotated_w, color=ORBIT_LINE_COLOR,
                                width=1.5, antialias=True, mode='line_strip',
                                glOptions='opaque'
                            )
                            dot = gl.GLScatterPlotItem(
                                pos=np.array([[sx_w, sy_w, sz_w]], dtype=np.float32),
                                color=dc, size=8, pxMode=True, glOptions='opaque'
                            )

                            trail_buf = np.empty((TRAIL_LEN, 3), dtype=np.float32)
                            trail_buf[:, 0] = sx_w
                            trail_buf[:, 1] = sy_w
                            trail_buf[:, 2] = sz_w

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

                            has_icon = self._has_icon_for_vessel(vessel_type)
                            dot.setVisible(not has_icon)
                            self.view.addItem(line)
                            self.view.addItem(dot)
                            self.view.addItem(trail_line)

                            self.render_objects[vid] = {
                                'line':              line,
                                'orbit_pts':         rotated_w,
                                'orbit_pts_local':   rotated,
                                'dot':               dot,
                                'trail_line':        trail_line,
                                'trail_buf':         trail_buf,
                                'trail_head':        0,
                                'trail_filled':      False,
                                'trail_colors':      trail_colors,
                                'base_trail_colors': trail_colors.copy(),
                                'base_line_color':   ORBIT_LINE_COLOR,
                                'base_dot_color':    dc,
                                'pos_3d':            (sx_w, sy_w, sz_w),
                                'pos_3d_local':      (sx, sy, sz),
                                'info_data':         info_data,
                                'color_idx':         cidx,
                                'ordered_trail':     trail_buf.copy(),
                                'R_matrix':          R,
                                'r_orbit':           r_orbit,
                                'ecc':               ecc,
                                'period':            period,
                                'true_anomaly_base': true_anom,
                                'last_update_time':  time.time(),
                                'body_name':         _body_name,
                                'is_lunar':          _is_lunar,
                                'vessel_type':       vessel_type,
                            }

                            # Estado de fundido para el oscurecido suave por hover
                            self._hover_current[vid] = 1.0
                            self._hover_targets[vid] = 1.0
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
                                if _is_lunar:
                                    mx, my, mz = self.moon_pos_3d
                                    sx_w, sy_w, sz_w = sx + mx, sy + my, sz + mz
                                else:
                                    sx_w, sy_w, sz_w = sx, sy, sz

                            obj['orbit_pts']         = rotated_w
                            obj['orbit_pts_local']   = rotated
                            obj['pos_3d']            = (sx_w, sy_w, sz_w)
                            obj['pos_3d_local']      = (sx, sy, sz)
                            obj['info_data']         = info_data
                            obj['R_matrix']          = R
                            obj['r_orbit']           = r_orbit
                            obj['ecc']               = ecc
                            obj['period']            = period
                            obj['true_anomaly_base'] = resolved_anom
                            obj['last_update_time']  = now_t
                            obj['body_name']         = _body_name
                            obj['is_lunar']          = _is_lunar

                            buf = obj['trail_buf']
                            head = obj['trail_head']
                            buf[head] = [sx_w, sy_w, sz_w]
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
                        self._hover_current.pop(vid, None)
                        self._hover_targets.pop(vid, None)
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
                    # Incluir la órbita de la Luna en el radio máximo para el encuadre inicial
                    if self.moon_render:
                        moon_sma = self.moon_render.get('r_orbit', 0)
                        max_orbit_radius = max(max_orbit_radius, moon_sma * 1.15)
                    target_distance = max(5200.0, max_orbit_radius * 2.2)
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
                            self._hover_current.pop(vid, None)
                            self._hover_targets.pop(vid, None)
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

                # ── Refrescar posición de la Luna desde KSP periódicamente ───────
                _now_pre = time.time()
                if _now_pre - self._moon_refresh_t > 2.0:
                    self._refresh_moon_from_ksp()
                    self._moon_refresh_t = _now_pre

                # Actualizar el siguiente satélite
                vessel = self.vessels_to_update[self.current_vessel_index]
                self.current_vessel_index += 1

                vid = vessel.name
                if vid not in self.vessel_streams or vid not in self.render_objects:
                    return

                # ── Detección del cuerpo orbitado ──────────────────────
                try:
                    _body_name = str(getattr(vessel.orbit.body, 'name', '') or '').strip()
                except Exception:
                    _body_name = self.render_objects[vid].get('body_name', '')
                _is_lunar = _is_lunar_body(_body_name)

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

                # ── Offset lunar ────────────────────────────────────
                if _is_lunar:
                    mx, my, mz = self.moon_pos_3d
                    _off      = np.array([mx, my, mz], dtype=np.float32)
                    rotated_w = rotated + _off
                    sx_w, sy_w, sz_w = sx + mx, sy + my, sz + mz
                    alt_km    = r_now - MUN_RADIUS_KM
                else:
                    rotated_w = rotated
                    sx_w, sy_w, sz_w = sx, sy, sz
                    alt_km    = r_now - KERBIN_RADIUS_KM

                vel_ms = 0.0
                try:
                    if streams['orbital_speed'] is not None:
                        vel_ms = streams['orbital_speed']()
                except Exception:
                    pass

                info_data = {
                    'alt_km':    alt_km,
                    'period':    period,
                    'inc':       inc,
                    'ecc':       ecc,
                    'vel_ms':    vel_ms,
                    'body_name': _body_name,
                    'is_lunar':  _is_lunar,
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
                    if _is_lunar:
                        mx, my, mz = self.moon_pos_3d
                        sx_w, sy_w, sz_w = sx + mx, sy + my, sz + mz
                    else:
                        sx_w, sy_w, sz_w = sx, sy, sz

                obj['orbit_pts']         = rotated_w
                obj['orbit_pts_local']   = rotated
                obj['pos_3d']            = (sx_w, sy_w, sz_w)
                obj['pos_3d_local']      = (sx, sy, sz)
                obj['info_data']         = info_data
                obj['R_matrix']          = R
                obj['r_orbit']           = r_orbit
                obj['ecc']               = ecc
                obj['period']            = period
                obj['true_anomaly_base'] = resolved_anom
                obj['last_update_time']  = now_t
                obj['body_name']         = _body_name
                obj['is_lunar']          = _is_lunar

                buf  = obj['trail_buf']
                head = obj['trail_head']
                buf[head] = [sx_w, sy_w, sz_w]
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

            # Animar la Luna primero para tener su posición actualizada
            self._animate_moon()

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

                    # Saltar completamente los satélites de grupos deshabilitados
                    if not self._is_vessel_group_enabled(obj.get('vessel_type', '')):
                        continue

                    dt = now - t0
                    true_anom = self._propagate_true_anomaly(ecc, period, ta_base, dt)

                    r_now = r_orbit * (1 - ecc ** 2) / (1 + ecc * math.cos(true_anom))
                    x_now = r_now * math.cos(true_anom)
                    y_now = r_now * math.sin(true_anom)
                    pos_now = R @ np.array([x_now, y_now, 0.0])
                    sx, sy, sz = float(pos_now[0]), float(pos_now[1]), float(pos_now[2])

                    # Aplicar offset lunar si procede
                    is_lunar = obj.get('is_lunar', False)
                    if is_lunar:
                        mx, my, mz = self.moon_pos_3d
                        sx_w, sy_w, sz_w = sx + mx, sy + my, sz + mz
                        # Actualizar órbita lunar con el offset actualizado de la Luna
                        orbit_local = obj.get('orbit_pts_local')
                        if orbit_local is not None:
                            _off = np.array([mx, my, mz], dtype=np.float32)
                            orbit_world = orbit_local + _off
                            obj['orbit_pts'] = orbit_world
                            show_in_map = selected is None or selected == vid
                            line = obj.get('line')
                            if line is not None and show_in_map:
                                line.setData(pos=orbit_world)
                    else:
                        sx_w, sy_w, sz_w = sx, sy, sz

                    obj['pos_3d']       = (sx_w, sy_w, sz_w)
                    obj['pos_3d_local'] = (sx, sy, sz)

                    show_in_map = selected is None or selected == vid
                    dot = obj.get('dot')
                    if dot is not None and show_in_map:
                        dot.setData(pos=np.array([[sx_w, sy_w, sz_w]], dtype=np.float32))

                except Exception:
                    continue

            # Transición suave del oscurecido por hover
            self._animate_hover_alpha()

            # Seguimiento de cámara fluido sobre el satélite seleccionado o el cuerpo celeste enfocado
            if selected is not None and selected in self.render_objects:
                self._focus_camera_on(selected, initial=False)
            elif getattr(self, 'camera_target_body', 'kerbin') == 'moon' and self.moon_render:
                mx, my, mz = self.moon_pos_3d
                anim_running = (
                    hasattr(self, '_camera_anim_obj') and 
                    self._camera_anim_obj is not None and 
                    self._camera_anim_obj.state() == QVariantAnimation.State.Running
                )
                if not anim_running:
                    self.view.setCameraPosition(pos=QVector3D(mx, my, mz))
                    self.view.update()
            
            if hasattr(self, 'icons_overlay') and self.icons_overlay is not None:
                self.icons_overlay.update()

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
                    elif is_click and self._press_vessel is None:
                        celestial = self._celestial_body_at_cursor(event)
                        if celestial is not None:
                            self._focus_body(celestial)
                        elif self.selected_vessel is not None:
                            self._deselect_vessel()
                self._press_pos = None
                self._press_vessel = None
                self.last_mouse_pos = None

        def _wheel_event(self, event):
            delta = event.angleDelta().y()
            factor = 0.9 if delta > 0 else 1.1
            new_dist = self.view.opts['distance'] * factor
            new_dist = max(700, min(35000, new_dist))
            self.view.setCameraPosition(distance=new_dist)
            self.view.update()
            if hasattr(self, 'icons_overlay') and self.icons_overlay is not None:
                self.icons_overlay.update()

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
                if hasattr(self, 'icons_overlay') and self.icons_overlay is not None:
                    self.icons_overlay.update()
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
            if hasattr(self, 'icons_overlay') and self.icons_overlay is not None:
                self.icons_overlay.setGeometry(0, 0, self.view.width(), self.view.height())
                self.icons_overlay.raise_()
            if hasattr(self, 'overlay') and self.overlay is not None:
                h = self.height() if self.height() > 0 else 800
                self.overlay.setGeometry(0, 0, 260, h)
                self.overlay.raise_()
            if hasattr(self, 'legend_widget') and self.legend_widget is not None:
                self.legend_widget.adjustSize()
                lw = self.legend_widget.width()
                lh = self.legend_widget.height()
                self.legend_widget.setGeometry(self.view.width() - lw - 15, self.view.height() - lh - 15, lw, lh)
                self.legend_widget.raise_()
            if hasattr(self, 'info_bubble') and self.info_bubble is not None:
                self.info_bubble.raise_()

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
    class KSPRealTimeVisualizer(QWidget):  # type: ignore
        back_clicked = pyqtSignal()
        def __init__(self, conn=None, parent=None):
            super().__init__(parent)
            self.timer = QTimer(self)
        def set_connection(self, conn):
            pass
        def _clear_all_vessels(self):
            pass