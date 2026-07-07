"""
Stub module for the Personal (Staff Management) feature.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton

from core_shared import GlassPanel, fade_in


class PersonalScreen(QWidget):
    back_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)

        self.panel = GlassPanel()
        self.panel.setObjectName("personalPanel")
        self.panel.setStyleSheet("""
            QFrame#personalPanel {
                background: #101d2c;
                border: 1px solid rgba(126, 164, 196, 90);
                border-radius: 14px;
            }
        """)
        root.addWidget(self.panel)

        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel_layout.setSpacing(24)

        title = QLabel("Módulo de Personal")
        title.setStyleSheet("color: #f3f8fc; font-size: 24px; font-weight: 700;")
        panel_layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)

        desc = QLabel("Este módulo se encuentra actualmente en desarrollo.")
        desc.setStyleSheet("color: #91a8bb; font-size: 15px;")
        panel_layout.addWidget(desc, alignment=Qt.AlignmentFlag.AlignCenter)

        back_btn = QPushButton("← Volver al Centro de Mando")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet("""
            QPushButton {
                background: #1d6f91;
                color: #f3fbff;
                border: 1px solid #66c7e8;
                border-radius: 9px;
                padding: 12px 20px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #2585aa;
                border-color: #9ee4f5;
            }
        """)
        back_btn.clicked.connect(self.back_clicked.emit)
        panel_layout.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        fade_in(self.panel, 180)
