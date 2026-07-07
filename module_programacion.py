"""
Module for the Programación (Scheduling / Manoeuvres) feature.
Provides a full control panel for planned launches and orbital manoeuvres.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt, QDate, QSize
from PyQt6.QtGui import QIcon, QPixmap, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QLineEdit, QTextEdit, QComboBox, QDateEdit, QDialog, QScrollArea,
    QToolButton, QListWidget, QListWidgetItem, QStackedWidget
)

from core_shared import (
    APP_NAME,
    LOGO_PATH_CORT,
    MANIOBRA_TYPES,
    ProgramacionStore,
    SatelliteStore,
    GlassPanel,
    _make_icon_pixmap,
    _normalize_key,
    fade_in,
)


# ─── Helper: small coloured icon buttons ──────────────────────────────────────

def _action_btn(icon_kind: str, tooltip: str, color: tuple[int, int, int] | None = None) -> QToolButton:
    btn = QToolButton()
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolTip(tooltip)
    btn.setAutoRaise(True)
    btn.setIconSize(QSize(20, 20))
    if color:
        pix = _make_icon_pixmap(icon_kind, 20, QColor(*color))
    else:
        pix = _make_icon_pixmap(icon_kind, 20)
    btn.setIcon(QIcon(pix))
    btn.setObjectName("iconToolButton")
    return btn


# ─── Satellite picker modal ───────────────────────────────────────────────────

class SatellitePickerDialog(QDialog):
    """Small modal listing all satellites so the user can pick one."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar satélite")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setStyleSheet("QDialog { background: #07111d; }")
        self.resize(560, 500)
        self._selected: str | None = None

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

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Elegir objeto / satélite")
        title.setObjectName("title")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f3f8fc;")
        header.addWidget(title)
        header.addStretch()
        close_btn = QPushButton("Cerrar")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        header.addWidget(close_btn)
        layout.addLayout(header)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar satélite…")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget { background: rgba(9,20,32,210); border-radius: 8px; }
            QListWidget::item { padding: 10px 14px; }
            QListWidget::item:selected { background: #1d6f91; }
        """)
        self.list_widget.itemDoubleClicked.connect(self._accept_selection)
        layout.addWidget(self.list_widget, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        ok_btn = QPushButton("Seleccionar")
        ok_btn.setObjectName("primaryButton")
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.clicked.connect(self._accept_selection)
        footer.addWidget(ok_btn)
        layout.addLayout(footer)

        self._load_satellites()

    def _load_satellites(self) -> None:
        store = SatelliteStore()
        self._all_names: list[str] = sorted(
            {r.get("name", "").strip() for r in store.visible_records() if r.get("name", "").strip()},
            key=str.lower,
        )
        self._populate(self._all_names)

    def _populate(self, names: list[str]) -> None:
        self.list_widget.clear()
        for name in names:
            item = QListWidgetItem(name)
            self.list_widget.addItem(item)

    def _filter(self, text: str) -> None:
        term = _normalize_key(text)
        if not term:
            self._populate(self._all_names)
            return
        filtered = [n for n in self._all_names if term in _normalize_key(n)]
        self._populate(filtered)

    def _accept_selection(self) -> None:
        item = self.list_widget.currentItem()
        if item:
            self._selected = item.text()
            self.accept()

    def selected_name(self) -> str | None:
        return self._selected


# ─── Add / Edit Maniobra dialog ───────────────────────────────────────────────

class ManiobrasFormDialog(QDialog):
    """Dialog for adding or editing a manoeuvre entry."""

    def __init__(
        self,
        record: dict | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._record = record
        self.setWindowTitle("Editar maniobra" if record else "Nueva maniobra")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setStyleSheet("QDialog { background: #07111d; }")
        self.resize(640, 520)

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

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 18, 22, 22)
        layout.setSpacing(14)

        # Title
        title_lbl = QLabel("Editar maniobra" if record else "Nueva maniobra")
        title_lbl.setStyleSheet("color:#f3f8fc; font-size:18px; font-weight:700;")
        layout.addWidget(title_lbl)

        # Objeto row
        obj_lbl = QLabel("Objeto")
        obj_lbl.setObjectName("muted")
        layout.addWidget(obj_lbl)

        obj_row = QHBoxLayout()
        obj_row.setSpacing(8)
        self.objeto_edit = QLineEdit()
        self.objeto_edit.setPlaceholderText("Nombre del objeto o satélite (escribe @ para buscar)")
        obj_row.addWidget(self.objeto_edit, 1)

        pick_btn = QPushButton("@  Elegir satélite")
        pick_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pick_btn.setStyleSheet("""
            QPushButton {
                background: rgba(29, 111, 145, 180);
                color: #f3fbff;
                border: 1px solid #66c7e8;
                border-radius: 9px;
                padding: 10px 16px;
                font-weight: 700;
            }
            QPushButton:hover { background: #2585aa; border-color: #9ee4f5; }
        """)
        pick_btn.clicked.connect(self._pick_satellite)
        obj_row.addWidget(pick_btn)
        layout.addLayout(obj_row)

        # Maniobra
        man_lbl = QLabel("Maniobra")
        man_lbl.setObjectName("muted")
        layout.addWidget(man_lbl)

        self.maniobra_combo = QComboBox()
        self.maniobra_combo.setEditable(True)
        self.maniobra_combo.addItems(MANIOBRA_TYPES)
        self.maniobra_combo.setCurrentIndex(-1)
        self.maniobra_combo.lineEdit().setPlaceholderText("Elige o escribe una maniobra…")
        layout.addWidget(self.maniobra_combo)

        # Detalles
        det_lbl = QLabel("Detalles")
        det_lbl.setObjectName("muted")
        layout.addWidget(det_lbl)

        self.detalles_edit = QTextEdit()
        self.detalles_edit.setPlaceholderText("Descripción libre de la operación…")
        self.detalles_edit.setMinimumHeight(100)
        self.detalles_edit.setMaximumHeight(140)
        layout.addWidget(self.detalles_edit)

        # Fecha prevista
        fecha_lbl = QLabel("Fecha prevista")
        fecha_lbl.setObjectName("muted")
        layout.addWidget(fecha_lbl)

        self.fecha_edit = QDateEdit()
        self.fecha_edit.setCalendarPopup(True)
        self.fecha_edit.setDate(QDate.currentDate())
        self.fecha_edit.setDisplayFormat("dd/MM/yyyy")
        layout.addWidget(self.fecha_edit)

        # Pre-fill if editing
        if record:
            self.objeto_edit.setText(str(record.get("objeto", "")))
            maniobra_val = str(record.get("maniobra", ""))
            if maniobra_val in MANIOBRA_TYPES:
                self.maniobra_combo.setCurrentText(maniobra_val)
            else:
                self.maniobra_combo.setCurrentText(maniobra_val)
            self.detalles_edit.setPlainText(str(record.get("detalles", "")))
            fecha_str = str(record.get("fecha", ""))
            fecha_obj = QDate.fromString(fecha_str, "dd/MM/yyyy")
            if not fecha_obj.isValid():
                fecha_obj = QDate.fromString(fecha_str, "yyyy-MM-dd")
            if fecha_obj.isValid():
                self.fecha_edit.setDate(fecha_obj)

        # Footer
        layout.addStretch()
        footer = QHBoxLayout()
        footer.addStretch()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Guardar")
        save_btn.setObjectName("primaryButton")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._on_save)
        footer.addWidget(cancel_btn)
        footer.addWidget(save_btn)
        layout.addLayout(footer)

        # Connect @ shortcut
        self.objeto_edit.textChanged.connect(self._check_at_trigger)

    def _check_at_trigger(self, text: str) -> None:
        if text.endswith("@"):
            current = text[:-1]
            self.objeto_edit.setText(current)
            self._pick_satellite()

    def _pick_satellite(self) -> None:
        dlg = SatellitePickerDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name = dlg.selected_name()
            if name:
                self.objeto_edit.setText(name)

    def _on_save(self) -> None:
        objeto = self.objeto_edit.text().strip()
        maniobra = self.maniobra_combo.currentText().strip()
        detalles = self.detalles_edit.toPlainText().strip()
        fecha = self.fecha_edit.date().toString("dd/MM/yyyy")

        if not objeto:
            QMessageBox.warning(self, APP_NAME, "El campo 'Objeto' es obligatorio.")
            return
        if not maniobra:
            QMessageBox.warning(self, APP_NAME, "El campo 'Maniobra' es obligatorio.")
            return
        self.accept()

    def result_payload(self) -> dict:
        return {
            "objeto": self.objeto_edit.text().strip(),
            "maniobra": self.maniobra_combo.currentText().strip(),
            "detalles": self.detalles_edit.toPlainText().strip(),
            "fecha": self.fecha_edit.date().toString("dd/MM/yyyy"),
        }


# ─── Main Programación Screen ─────────────────────────────────────────────────

class ProgramacionScreen(QWidget):
    back_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = ProgramacionStore()
        self._build_ui()
        self._refresh_table()

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        # ── Header panel ─────────────────────────────────────────────────────
        header_panel = GlassPanel()
        header_layout = QHBoxLayout(header_panel)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(14)

        logo = QLabel()
        logo_pix = QPixmap(str(LOGO_PATH_CORT)) if LOGO_PATH_CORT.exists() else QPixmap()
        if not logo_pix.isNull():
            logo.setPixmap(logo_pix.scaledToWidth(180, Qt.TransformationMode.SmoothTransformation))
        else:
            logo.setText(APP_NAME)
            logo.setStyleSheet("color:#dce9f6; font-size:16px; font-weight:700;")
        header_layout.addWidget(logo)

        title_lbl = QLabel("Programación de Maniobras")
        title_lbl.setStyleSheet("color:#f3f8fc; font-size:20px; font-weight:700;")
        header_layout.addWidget(title_lbl)

        header_layout.addStretch()

        add_btn = QToolButton()
        add_btn.setText("+")
        add_btn.setToolTip("Nueva maniobra")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setObjectName("pressMenuButton")
        add_btn.setFixedSize(38, 38)
        add_btn.clicked.connect(self._on_add)
        header_layout.addWidget(add_btn)

        back_btn = QPushButton("← Volver")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet("""
            QPushButton {
                background: rgba(29,111,145,160);
                color: #f3fbff;
                border: 1px solid #66c7e8;
                border-radius: 9px;
                padding: 10px 18px;
                font-weight: 700;
            }
            QPushButton:hover { background: #2585aa; border-color: #9ee4f5; }
        """)
        back_btn.clicked.connect(self.back_clicked.emit)
        header_layout.addWidget(back_btn)

        root.addWidget(header_panel)

        # ── Table panel ───────────────────────────────────────────────────────
        table_panel = GlassPanel()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(14, 14, 14, 14)
        table_layout.setSpacing(10)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Objeto", "Maniobra", "Detalles", "Fecha prevista", "Acciones"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setMinimumSectionSize(80)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background: transparent;
                border: none;
                gridline-color: rgba(126, 164, 196, 45);
                selection-background-color: rgba(29, 111, 145, 90);
            }
            QHeaderView::section {
                background: rgba(9, 20, 32, 200);
                color: #9fc7dc;
                border: none;
                border-right: 1px solid rgba(126, 164, 196, 55);
                border-bottom: 2px solid rgba(100, 180, 220, 90);
                padding: 10px 16px;
                font-weight: 700;
                font-size: 13px;
                text-align: left;
            }
            QHeaderView::section:last {
                border-right: none;
            }
            QTableWidget::item {
                padding: 0px 16px;
                border: none;
                color: #dce9f6;
            }
            QTableWidget::item:selected {
                background: rgba(29, 111, 145, 90);
                color: #f3f8fc;
            }
            QTableWidget::item:alternate {
                background: rgba(13, 28, 43, 100);
            }
        """)
        table_layout.addWidget(self.table)

        self._empty_label = QLabel("No hay maniobras programadas. Usa el botón + para añadir una.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setObjectName("muted")
        self._empty_label.setVisible(False)
        table_layout.addWidget(self._empty_label)

        root.addWidget(table_panel, 1)
        fade_in(self, 180)

    # ── Table management ─────────────────────────────────────────────────────

    def _refresh_table(self) -> None:
        records = self.store.get_all()
        self.table.setRowCount(0)

        if not records:
            self.table.setVisible(False)
            self._empty_label.setVisible(True)
            return

        self.table.setVisible(True)
        self._empty_label.setVisible(False)
        self.table.setRowCount(len(records))

        for row, record in enumerate(records):
            self.table.setRowHeight(row, 52)

            for col, key in enumerate(["objeto", "maniobra", "detalles", "fecha"]):
                text = str(record.get(key, ""))
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self.table.setItem(row, col, item)

            # Actions cell
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(8, 4, 8, 4)
            actions_layout.setSpacing(6)
            actions_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            record_id = int(record.get("id", 0))

            # Delete (X, red)
            del_btn = _action_btn("globe", "Eliminar maniobra", (220, 60, 60))
            del_btn.setText("✕")
            del_btn.setIcon(QIcon())
            del_btn.setStyleSheet("""
                QToolButton {
                    color: #e05050;
                    font-weight: 900;
                    font-size: 15px;
                    border: 1px solid rgba(220,60,60,120);
                    border-radius: 6px;
                    padding: 4px 8px;
                    background: rgba(220,60,60,30);
                }
                QToolButton:hover { background: rgba(220,60,60,80); border-color: #e05050; }
            """)
            del_btn.clicked.connect(lambda _=False, rid=record_id: self._on_delete(rid))
            actions_layout.addWidget(del_btn)

            # Edit (pencil)
            edit_btn = _action_btn("edit", "Editar maniobra")
            edit_btn.setText("✎")
            edit_btn.setIcon(QIcon())
            edit_btn.setStyleSheet("""
                QToolButton {
                    color: #7ec8e8;
                    font-weight: 900;
                    font-size: 15px;
                    border: 1px solid rgba(126,196,232,100);
                    border-radius: 6px;
                    padding: 4px 8px;
                    background: rgba(29,111,145,40);
                }
                QToolButton:hover { background: rgba(29,111,145,100); border-color: #7ec8e8; }
            """)
            edit_btn.clicked.connect(lambda _=False, rid=record_id: self._on_edit(rid))
            actions_layout.addWidget(edit_btn)

            # Mark complete (check, green)
            done_btn = _action_btn("reload", "Marcar como completada")
            done_btn.setText("✔")
            done_btn.setIcon(QIcon())
            done_btn.setStyleSheet("""
                QToolButton {
                    color: #50c878;
                    font-weight: 900;
                    font-size: 15px;
                    border: 1px solid rgba(80,200,120,100);
                    border-radius: 6px;
                    padding: 4px 8px;
                    background: rgba(40,140,80,30);
                }
                QToolButton:hover { background: rgba(40,140,80,100); border-color: #50c878; }
            """)
            done_btn.clicked.connect(lambda _=False, rid=record_id: self._on_complete(rid))
            actions_layout.addWidget(done_btn)

            self.table.setCellWidget(row, 4, actions_widget)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _on_add(self) -> None:
        dlg = ManiobrasFormDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        p = dlg.result_payload()
        self.store.add(p["objeto"], p["maniobra"], p["detalles"], p["fecha"])
        self._refresh_table()

    def _on_edit(self, record_id: int) -> None:
        record = self.store.get_by_id(record_id)
        if record is None:
            return
        dlg = ManiobrasFormDialog(record=record, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        p = dlg.result_payload()
        self.store.update(record_id, p["objeto"], p["maniobra"], p["detalles"], p["fecha"])
        self._refresh_table()

    def _on_delete(self, record_id: int) -> None:
        record = self.store.get_by_id(record_id)
        if record is None:
            return
        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"¿Eliminar la maniobra «{record.get('objeto', '')} — {record.get('maniobra', '')}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.delete(record_id)
        self._refresh_table()

    def _on_complete(self, record_id: int) -> None:
        record = self.store.get_by_id(record_id)
        if record is None:
            return
        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"¿Marcar la maniobra «{record.get('objeto', '')} — {record.get('maniobra', '')}» como completada y eliminarla?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.delete(record_id)
        self._refresh_table()
