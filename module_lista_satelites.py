"""
Module for the Satellite List feature of Terranova Aerospace.
Contains dialogs, filters, sorting options, and the main satellite list screen.
"""

from __future__ import annotations

import math
from pathlib import Path

from PyQt6.QtCore import pyqtSignal, Qt, QSize, QUrl, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QBrush, QColor
from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QComboBox, QListWidget, QListWidgetItem,
    QFileDialog, QDialogButtonBox, QCheckBox, QFrame, QGridLayout, QHBoxLayout,
    QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QApplication, QStackedWidget, QTextEdit, QLineEdit, QScrollArea, QDialog,
    QToolButton
)

# Conditional import for video widgets
try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    _MULTIMEDIA_AVAILABLE = True
except Exception:
    QAudioOutput = None  # type: ignore
    QMediaPlayer = None  # type: ignore
    QVideoWidget = None  # type: ignore
    _MULTIMEDIA_AVAILABLE = False

from core_shared import (
    BASE_DIR,
    APP_NAME,
    LOGO_PATH_CORT,
    SATELLITES_PAGE_SIZE,
    SATELLITE_STATUS_ACTIVE,
    SATELLITE_STATUS_MAINTENANCE,
    SATELLITE_STATUS_OFFLINE,
    SatelliteStore,
    GlassPanel,
    SpinnerWidget,
    _elide_text,
    _shorten_text,
    _normalize_key,
    _make_icon_pixmap,
    _format_ksp_ut,
    _auto_group_for_altitude,
    fade_in,
    fade_out
)


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
        # We need QToolButton from PyQt6
        from PyQt6.QtWidgets import QToolButton
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
