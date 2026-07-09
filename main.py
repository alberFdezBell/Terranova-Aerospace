"""
Main entry point for Terranova Aerospace.
Handles authentication, loading, main navigation (Command Center), and internal modules.
"""

from __future__ import annotations

import random
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QIcon, QPixmap, QIntValidator
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QHBoxLayout, QScrollArea, QFrame, QGridLayout, QStackedWidget, QMainWindow,
    QMessageBox, QToolButton
)

# Shared core imports
from core_shared import (
    BASE_DIR,
    APP_NAME,
    LOGO_PATH,
    LOGO_PATH_CORT,
    PANEL_IMAGE_DIR,
    MODULES,
    MODULE_PANEL_IMAGES,
    INITIAL_STATUS,
    MODULE_STATUS,
    DEFAULT_KRPC_IP,
    DEFAULT_KRPC_PORT,
    _KSP_AVAILABLE,
    _active_ksp_save_context,
    connect_to_ksp_async,
    fade_in,
    fade_out,
    AuthManager,
    KrpcConfigManager,
    KrpcSettingsDialog,
    LogoLabel,
    SpinnerWidget,
    GlassPanel,
    ModuleCard
)

# Business module imports
from module_mapa_orbital import KSPRealTimeVisualizer
from module_notas_prensa import PressModuleScreen
from module_lista_satelites import SatelliteListScreen

# Stub module imports
from module_programacion import ProgramacionScreen
from module_centro_mando import CentroMandoScreen
from module_personal import PersonalScreen


class LoginScreen(QWidget):
    def __init__(self, auth: AuthManager, on_success, parent: QWidget | None = None):
        super().__init__(parent)
        self.auth = auth
        self.krpc_config = KrpcConfigManager()
        self.on_success = on_success
        self.is_first_run = not auth.has_user()
        self._build_ui()
        fade_in(self.panel)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.panel = GlassPanel()
        self.panel.setObjectName("glassPanel")
        self.panel.setMaximumWidth(500)
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(42, 38, 42, 38)
        panel_layout.setSpacing(18)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.addStretch(1)
        self.settings_button = QToolButton()
        self.settings_button.setObjectName("krpcSettingsButton")
        self.settings_button.setText("⚙")
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setToolTip("Configurar IP y puerto de kRPC")
        self.settings_button.setFixedSize(34, 34)
        self.settings_button.clicked.connect(self._open_krpc_settings)
        header_row.addWidget(self.settings_button)
        panel_layout.addLayout(header_row)

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

        self.krpc_ip_input = QLineEdit()
        self.krpc_ip_input.setPlaceholderText(f"IP de kRPC (por defecto {DEFAULT_KRPC_IP})")
        self.krpc_ip_input.setVisible(self.is_first_run)
        panel_layout.addWidget(self.krpc_ip_input)

        self.krpc_port_input = QLineEdit()
        self.krpc_port_input.setPlaceholderText(f"Puerto de kRPC (por defecto {DEFAULT_KRPC_PORT})")
        self.krpc_port_input.setValidator(QIntValidator(1, 65535, self))
        self.krpc_port_input.setVisible(self.is_first_run)
        panel_layout.addWidget(self.krpc_port_input)

        if self.is_first_run:
            current_krpc = self.krpc_config.load()
            self.krpc_ip_input.setText(current_krpc["krpc_ip"])
            self.krpc_port_input.setText(str(current_krpc["krpc_port"]))

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

            krpc_ip = self.krpc_ip_input.text().strip() or DEFAULT_KRPC_IP
            krpc_port_text = self.krpc_port_input.text().strip() or str(DEFAULT_KRPC_PORT)
            try:
                krpc_port = int(krpc_port_text)
                if not (1 <= krpc_port <= 65535):
                    raise ValueError
            except ValueError:
                self._set_error("El puerto de kRPC debe ser un número entre 1 y 65535.")
                return

            try:
                self.auth.create_user(username, password)
                self.krpc_config.save(krpc_ip, krpc_port)
            except OSError as exc:
                self._set_error(f"No se pudo guardar la configuración: {exc}")
                return
            self.on_success()
            return

        if self.auth.verify_password(password):
            self.on_success()
        else:
            self._set_error("Credenciales no válidas.")

    def _open_krpc_settings(self) -> None:
        dialog = KrpcSettingsDialog(self.krpc_config, self)
        dialog.exec()

    def _set_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.password_input.selectAll()
        self.password_input.setFocus()


class StartupLoadingScreen(QWidget):
    def __init__(self, on_finished, ksp_callbacks=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.on_finished = on_finished
        self.ksp_callbacks = ksp_callbacks
        self.messages = INITIAL_STATUS
        self._ksp_thread = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(22)

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


class CommandCenter(QWidget):
    def __init__(self, on_module_selected, on_reload_clicked=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.on_module_selected = on_module_selected
        self.on_reload_clicked = on_reload_clicked
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

        # Botón de recarga
        if self.on_reload_clicked:
            reload_btn = QPushButton("↻ Recargar")
            reload_btn.setObjectName("reloadButton")
            reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            reload_btn.setFixedSize(110, 34)
            reload_btn.clicked.connect(self.on_reload_clicked)
            header_layout.addWidget(reload_btn, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

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

        # === AQUÍ ESTÁ EL TRUCO PARA CENTRAR TODO EL BLOQUE ===
        # Creamos un contenedor intermedio horizontal
        centering_widget = QWidget()
        centering_layout = QHBoxLayout(centering_widget)
        centering_layout.setContentsMargins(0, 0, 0, 0)
        
        # 1. Empuje izquierdo
        centering_layout.addStretch(1)

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
            # Aseguramos que se añadan con alineación al centro por si acaso
            self.grid.addWidget(card, row, col, alignment=Qt.AlignmentFlag.AlignCenter)

        # Añadimos el contenedor del grid al layout centrado
        centering_layout.addWidget(grid_container)
        
        # 2. Empuje derecho
        centering_layout.addStretch(1)
        
        # Añadimos el bloque centrado al layout principal del contenido
        content_layout.addWidget(centering_widget)
        # ======================================================

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
            self.grid.addWidget(card, row, col, alignment=Qt.AlignmentFlag.AlignCenter)
            
        # Al quitar el loop que hacía self.grid.setColumnStretch(col, 1),
        # las columnas ya no se separarán artificialmente.


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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.auth = AuthManager()
        self.setWindowTitle(APP_NAME)
        self.resize(1120, 800)
        self.setMinimumSize(800, 560)

        self._ksp_conn = None
        self._ksp_error: str | None = None
        self._ksp_thread = None

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.login = LoginScreen(self.auth, self.show_startup_loading)
        self.startup = StartupLoadingScreen(
            on_finished=self.show_command_center,
            ksp_callbacks=(self._on_ksp_connected, self._on_ksp_failed),
        )
        self.command = CommandCenter(
            on_module_selected=self.prepare_module,
            on_reload_clicked=self._reload_application,
        )
        self.transition = ModuleTransitionScreen()

        self.stack.addWidget(self.login)
        self.stack.addWidget(self.startup)
        self.stack.addWidget(self.command)
        self.stack.addWidget(self.transition)

        # Operational Modules
        self.visualizer = KSPRealTimeVisualizer(conn=self._ksp_conn)
        self.stack.addWidget(self.visualizer)
        self.visualizer.back_clicked.connect(self.show_command_center)

        self.satellite_list = SatelliteListScreen(self._open_orbital_map_from_list)
        self.stack.addWidget(self.satellite_list)
        self.satellite_list.back_clicked.connect(self.show_command_center)

        self.press_module = PressModuleScreen(self.show_command_center)
        self.stack.addWidget(self.press_module)

        # Stub Modules
        self.programacion = ProgramacionScreen()
        self.stack.addWidget(self.programacion)
        self.programacion.back_clicked.connect(self.show_command_center)

        self.centro_mando = CentroMandoScreen()
        self.stack.addWidget(self.centro_mando)
        self.centro_mando.back_clicked.connect(self.show_command_center)

        self.personal = PersonalScreen()
        self.stack.addWidget(self.personal)
        self.personal.back_clicked.connect(self.show_command_center)

    def _on_ksp_connected(self, conn) -> None:
        self._ksp_conn = conn
        self._ksp_error = None
        if self.visualizer is not None:
            self.visualizer.set_connection(conn)
        if self.satellite_list is not None:
            self.satellite_list.set_connection(conn)

    def _on_ksp_failed(self, err: str) -> None:
        self._ksp_conn = None
        self._ksp_error = err

    def show_startup_loading(self) -> None:
        self.stack.setCurrentWidget(self.startup)
        QTimer.singleShot(50, self.startup.start)

    def show_command_center(self) -> None:
        self.stack.setCurrentWidget(self.command)
        fade_in(self.command, 650)

    def prepare_module(self, module_name: str) -> None:
        target = MODULES.get(module_name)
        if not target:
            QMessageBox.information(self, APP_NAME, "Módulo no disponible actualmente.")
            return

        if target == "internal":
            fade_out(self.command, lambda: self._show_transition(module_name, target))
            return

        # External modules fallback
        target_path = BASE_DIR / target
        if not target_path.exists():
            QMessageBox.warning(self, APP_NAME, f"No se encontró el módulo: {target}")
            return
        fade_out(self.command, lambda: self._show_transition(module_name, target))

    def _show_transition(self, module_name: str, target: str) -> None:
        self.stack.setCurrentWidget(self.transition)
        self.transition.start(module_name, target, self.launch_module)

    def launch_module(self, module_name: str, target: str) -> None:
        if module_name == "Mapa orbital":
            self._launch_orbital_map()
            return
        if module_name == "Lista de satélites":
            self._launch_satellite_list()
            return
        if module_name == "Notas de prensa":
            self._launch_press_notes()
            return
        if module_name == "Programación":
            self._launch_programacion()
            return
        if module_name == "Centro de mando":
            self._launch_centro_mando()
            return
        if module_name == "Personal":
            self._launch_personal()
            return

        # External modules fallback
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

    def _launch_programacion(self) -> None:
        self.stack.setCurrentWidget(self.programacion)
        fade_in(self.programacion, 650)
        self.statusBar().showMessage("Programación iniciada", 5000)

    def _launch_centro_mando(self) -> None:
        self.stack.setCurrentWidget(self.centro_mando)
        fade_in(self.centro_mando, 650)
        self.statusBar().showMessage("Centro de mando iniciado", 5000)

    def _launch_personal(self) -> None:
        self.stack.setCurrentWidget(self.personal)
        fade_in(self.personal, 650)
        self.statusBar().showMessage("Personal iniciado", 5000)

    def _reload_application(self) -> None:
        self.close()
        subprocess.Popen([sys.executable, __file__])
        QApplication.quit()

    def closeEvent(self, event) -> None:
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
    QPushButton#reloadButton {
        background: #1d6f91;
        color: #f3fbff;
        border: 1px solid #66c7e8;
        border-radius: 9px;
        padding: 6px 12px;
        font-weight: 700;
    }
    QPushButton#reloadButton:hover {
        background: #2585aa;
        border-color: #9ee4f5;
    }
    QToolButton#krpcSettingsButton {
        background: rgba(13, 28, 43, 200);
        color: #9fc7dc;
        border: 1px solid rgba(126, 164, 196, 90);
        border-radius: 17px;
        font-size: 16px;
        font-weight: 700;
    }
    QToolButton#krpcSettingsButton:hover {
        background: rgba(23, 45, 65, 240);
        border-color: rgba(137, 213, 241, 220);
        color: #ffffff;
    }
    QToolButton#krpcSettingsButton:pressed {
        background: rgba(32, 58, 80, 250);
        border-color: rgba(163, 230, 248, 235);
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
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())