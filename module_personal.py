"""
Module for the Personal (Staff Management) feature.
Provides a full control panel for active personnel.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QLineEdit, QDialog, QToolButton, QGridLayout, QSpinBox
)

from core_shared import (
    APP_NAME,
    LOGO_PATH_CORT,
    PersonalStore,
    GlassPanel,
    _make_icon_pixmap,
    fade_in,
)


# ─── Helper ───────────────────────────────────────────────────────────────────

def _action_btn(symbol: str, tooltip: str, style: str) -> QToolButton:
    btn = QToolButton()
    btn.setText(symbol)
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(style)
    btn.setObjectName("iconToolButton")
    return btn


# ─── Add / Edit Employee dialog ───────────────────────────────────────────────

class PersonalFormDialog(QDialog):
    """Dialog for adding or editing an employee entry."""

    def __init__(self, record: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._record = record
        self.setWindowTitle("Editar empleado" if record else "Nuevo empleado")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setStyleSheet("QDialog { background: #07111d; }")
        self.resize(560, 420)

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

        title_lbl = QLabel("Editar empleado" if record else "Nuevo empleado")
        title_lbl.setStyleSheet("color:#f3f8fc; font-size:18px; font-weight:700;")
        layout.addWidget(title_lbl)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)

        # Nombre
        form.addWidget(self._lbl("Nombre"), 0, 0)
        self.nombre_edit = QLineEdit()
        self.nombre_edit.setPlaceholderText("Nombre del empleado")
        form.addWidget(self.nombre_edit, 0, 1)

        # Apellidos
        form.addWidget(self._lbl("Apellidos"), 1, 0)
        self.apellidos_edit = QLineEdit()
        self.apellidos_edit.setPlaceholderText("Apellidos del empleado")
        form.addWidget(self.apellidos_edit, 1, 1)

        # Edad
        form.addWidget(self._lbl("Edad"), 2, 0)
        self.edad_edit = QLineEdit()
        self.edad_edit.setPlaceholderText("Edad (años)")
        form.addWidget(self.edad_edit, 2, 1)

        # Puesto
        form.addWidget(self._lbl("Puesto"), 3, 0)
        self.puesto_edit = QLineEdit()
        self.puesto_edit.setPlaceholderText("Puesto o cargo")
        form.addWidget(self.puesto_edit, 3, 1)

        layout.addLayout(form)

        # Pre-fill
        if record:
            self.nombre_edit.setText(str(record.get("nombre", "")))
            self.apellidos_edit.setText(str(record.get("apellidos", "")))
            self.edad_edit.setText(str(record.get("edad", "")))
            self.puesto_edit.setText(str(record.get("puesto", "")))

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

    @staticmethod
    def _lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("muted")
        return lbl

    def _on_save(self) -> None:
        nombre = self.nombre_edit.text().strip()
        apellidos = self.apellidos_edit.text().strip()
        edad = self.edad_edit.text().strip()
        puesto = self.puesto_edit.text().strip()

        if not nombre:
            QMessageBox.warning(self, APP_NAME, "El campo 'Nombre' es obligatorio.")
            return
        if not apellidos:
            QMessageBox.warning(self, APP_NAME, "El campo 'Apellidos' es obligatorio.")
            return
        self.accept()

    def result_payload(self) -> dict:
        return {
            "nombre": self.nombre_edit.text().strip(),
            "apellidos": self.apellidos_edit.text().strip(),
            "edad": self.edad_edit.text().strip(),
            "puesto": self.puesto_edit.text().strip(),
        }


# ─── Main Personal Screen ─────────────────────────────────────────────────────

class PersonalScreen(QWidget):
    back_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = PersonalStore()
        self._search_text = ""
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

        title_lbl = QLabel("Panel de Personal")
        title_lbl.setStyleSheet("color:#f3f8fc; font-size:20px; font-weight:700;")
        header_layout.addWidget(title_lbl)

        header_layout.addStretch()

        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar por nombre, apellidos o edad…")
        self.search_input.setFixedWidth(280)
        self.search_input.textChanged.connect(self._on_search_changed)
        header_layout.addWidget(self.search_input)

        # Add button
        add_btn = QToolButton()
        add_btn.setText("+")
        add_btn.setToolTip("Nuevo empleado")
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
            ["Nombre", "Apellidos", "Edad", "Puesto", "Acciones"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
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

        self._empty_label = QLabel("No hay empleados registrados. Usa el botón + para añadir uno.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setObjectName("muted")
        self._empty_label.setVisible(False)
        table_layout.addWidget(self._empty_label)

        self._no_results_label = QLabel("No se encontraron resultados para la búsqueda.")
        self._no_results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_results_label.setObjectName("muted")
        self._no_results_label.setVisible(False)
        table_layout.addWidget(self._no_results_label)

        root.addWidget(table_panel, 1)
        fade_in(self, 180)

    # ── Table management ─────────────────────────────────────────────────────

    def _on_search_changed(self, text: str) -> None:
        self._search_text = text
        self._refresh_table()

    def _refresh_table(self) -> None:
        records = self.store.query(self._search_text)
        all_records = self.store.get_all()

        self._empty_label.setVisible(False)
        self._no_results_label.setVisible(False)

        if not all_records:
            self.table.setVisible(False)
            self._empty_label.setVisible(True)
            return

        if not records:
            self.table.setVisible(False)
            self._no_results_label.setVisible(True)
            return

        self.table.setVisible(True)
        self.table.setRowCount(len(records))

        for row, record in enumerate(records):
            self.table.setRowHeight(row, 52)

            for col, key in enumerate(["nombre", "apellidos", "edad", "puesto"]):
                text = str(record.get(key, ""))
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self.table.setItem(row, col, item)

            # Actions cell
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(8, 4, 8, 4)
            actions_layout.setSpacing(8)
            actions_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            record_id = int(record.get("id", 0))

            # Delete (X, red)
            del_btn = _action_btn("✕", "Eliminar empleado", """
                QToolButton {
                    color: #e05050;
                    font-weight: 900;
                    font-size: 15px;
                    border: 1px solid rgba(220,60,60,120);
                    border-radius: 6px;
                    padding: 4px 10px;
                    background: rgba(220,60,60,30);
                }
                QToolButton:hover { background: rgba(220,60,60,80); border-color: #e05050; }
            """)
            del_btn.clicked.connect(lambda _=False, rid=record_id: self._on_delete(rid))
            actions_layout.addWidget(del_btn)

            # Edit (pencil)
            edit_btn = _action_btn("✎", "Editar empleado", """
                QToolButton {
                    color: #7ec8e8;
                    font-weight: 900;
                    font-size: 15px;
                    border: 1px solid rgba(126,196,232,100);
                    border-radius: 6px;
                    padding: 4px 10px;
                    background: rgba(29,111,145,40);
                }
                QToolButton:hover { background: rgba(29,111,145,100); border-color: #7ec8e8; }
            """)
            edit_btn.clicked.connect(lambda _=False, rid=record_id: self._on_edit(rid))
            actions_layout.addWidget(edit_btn)

            self.table.setCellWidget(row, 4, actions_widget)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _on_add(self) -> None:
        dlg = PersonalFormDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        p = dlg.result_payload()
        self.store.add(p["nombre"], p["apellidos"], p["edad"], p["puesto"])
        self._refresh_table()

    def _on_edit(self, record_id: int) -> None:
        record = self.store.get_by_id(record_id)
        if record is None:
            return
        dlg = PersonalFormDialog(record=record, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        p = dlg.result_payload()
        self.store.update(record_id, p["nombre"], p["apellidos"], p["edad"], p["puesto"])
        self._refresh_table()

    def _on_delete(self, record_id: int) -> None:
        record = self.store.get_by_id(record_id)
        if record is None:
            return
        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"¿Eliminar al empleado «{record.get('nombre', '')} {record.get('apellidos', '')}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.delete(record_id)
        self._refresh_table()
