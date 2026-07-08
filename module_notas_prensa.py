"""
Module for the Press Notes/Newsroom feature.
Contains editors, viewers, dialogs, lists, and main press screen.
"""

from __future__ import annotations

import html
import mimetypes
from pathlib import Path

from PyQt6.QtCore import pyqtSignal, Qt, QRectF, QSize, QUrl, QDate, QEvent, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QFont, QFontMetrics, QTextCursor, QTextDocument, QAction, QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QFrame,
    QScrollArea, QStackedWidget, QListWidget, QListWidgetItem, QFileDialog,
    QDateEdit, QGridLayout, QMessageBox, QTextEdit, QTextBrowser, QMenu, QToolButton,
    QMainWindow, QApplication, QGraphicsOpacityEffect, QDialog, QSizePolicy
)

from core_shared import (
    BASE_DIR,
    APP_NAME,
    LOGO_PATH,
    LOGO_PATH_CORT,
    _MULTIMEDIA_AVAILABLE,
    _PDF_AVAILABLE,
    QAudioOutput,
    QMediaPlayer,
    QVideoWidget,
    QPdfDocument,
    QPdfView,
    PressStore,
    GlassPanel,
    SpinnerWidget,
    LogoLabel,
    fade_in,
    fade_out,
    _press_date_sort_key,
    _press_plain_text_from_html,
    _press_summary_from_blocks,
    _press_summary_from_text,
    _press_legacy_body_and_attachments,
    _press_media_kind_for_path,
    _press_encode_attachment_ref,
    _press_decode_attachment_ref,
    _press_rewrite_attachment_refs,
    _press_crop_rect_from_payload,
    _press_crop_payload_from_rect,
    _press_center_horizontal_crop,
    _press_crop_image,
    _press_pixmap_to_data_uri,
    _press_relativize_path,
    _resolve_press_path,
    _shorten_text,
    _normalize_key
)

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation


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
        from PyQt6.QtCore import QPointF
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

    def _handle_at_point(self, pos) -> str:
        for name, rect in self._handle_rects().items():
            if rect.contains(pos):
                return name
        return ""

    def _selection_from_corner(self, handle: str, pos) -> QRectF:
        from PyQt6.QtCore import QPointF
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

    def __init__(self, html_content: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("pressBlock")
        self.setProperty("kind", "text")
        self._build_ui(html_content)

    def _build_ui(self, html_content: str) -> None:
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
        if html_content:
            self.editor.setHtml(html_content)
        layout.addWidget(self.editor)

    def set_html(self, html_content: str) -> None:
        if html_content:
            self.editor.setHtml(html_content)
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

    def add_text_block(self, html_content: str = "", focus: bool = False, index: int | None = None) -> PressTextBlockWidget:
        widget = PressTextBlockWidget(html_content)
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
                html_content = widget.html() if text else ""
                if not text and not html_content.strip():
                    continue
                result.append({"type": "text", "html": html_content, "plain": text})
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
        
        self.resize(950, 700) 
        self.setStyleSheet("QWidget { background: #07111d; }")
        
        screen = self.screen() if self.screen() else QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            x = screen_geo.x() + (screen_geo.width() - self.width()) // 2
            y = screen_geo.y() + (screen_geo.height() - self.height()) // 2
            self.move(x, y)

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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        form_layout = QVBoxLayout(scroll_content)
        form_layout.setContentsMargins(0, 0, 4, 0)
        form_layout.setSpacing(14)

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
        self.editor.setMinimumHeight(250)
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
        self.attachments.setMinimumHeight(120)
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

        scroll.setWidget(scroll_content)
        panel_layout.addWidget(scroll, 1)

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

        text_widget = QWidget()
        text_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QVBoxLayout(text_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)
        self.title_label = QLabel(str(self.note.get("title", "")) or "Sin título")
        self.title_label.setObjectName("transitionTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        top.addWidget(self.title_label, 1)
        layout.addLayout(top)

        importance = str(self.note.get("importance", "")).strip()
        if importance:
            chip = QLabel(importance)
            chip.setObjectName("stateChip")
            chip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            layout.addWidget(chip, alignment=Qt.AlignmentFlag.AlignLeft)

        summary = QLabel(self._summary_text())
        summary.setWordWrap(True)
        summary.setObjectName("muted")
        summary.setTextFormat(Qt.TextFormat.PlainText)
        summary.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        summary.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(summary)

        meta = QLabel(self._meta_text())
        meta.setObjectName("muted")
        meta.setWordWrap(True)
        meta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(meta)

        outer.addWidget(text_widget, 1)

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
        import math
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
        import math
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

    def _press_fade_to(self, target_widget: QWidget, post_switch=None) -> None:
        current = self.stack.currentWidget()
        FADE_OUT_MS = 160
        FADE_IN_MS  = 220

        def _do_switch():
            self.stack.setCurrentWidget(target_widget)
            if post_switch:
                post_switch()
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
