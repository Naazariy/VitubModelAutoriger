import numpy as np
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtCore import Qt, QPoint, Signal
from typing import Optional
from src.core.mesh import Mesh
from src.renderer.renderer import MeshRenderer

class ViewportWidget(QOpenGLWidget):
    """
    Interactive PySide6 OpenGL viewport for real-time 2.5D deformation rendering.
    Supports depth painting brush and mouse navigation.
    """
    depth_brushed = Signal(float, float) # (norm_x, norm_y)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 400)
        self.renderer = MeshRenderer()
        
        self.mesh: Optional[Mesh] = None
        self.positions_2d: Optional[np.ndarray] = None
        self.rotated_3d: Optional[np.ndarray] = None
        self.view_mode: str = "Textured"
        
        self.brush_active: bool = False
        self.mouse_pressed: bool = False

    def initializeGL(self):
        self.renderer.initialize_gl()

    def update_render_data(
        self,
        mesh: Mesh,
        positions_2d: np.ndarray,
        rotated_3d: np.ndarray,
        view_mode: str = "Textured"
    ):
        self.mesh = mesh
        self.positions_2d = positions_2d
        self.rotated_3d = rotated_3d
        self.view_mode = view_mode
        self.update()

    def set_texture(self, rgba_image: np.ndarray):
        # ensure initializeGL has run, or the renderer buffers the texture
        self.renderer.set_texture(rgba_image)
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self.brush_active:
            self.mouse_pressed = True
            self._emit_brush_event(event.position().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.mouse_pressed and self.brush_active:
            self._emit_brush_event(event.position().toPoint())

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.mouse_pressed = False

    def _emit_brush_event(self, pt: QPoint):
        w, h = self.width(), self.height()
        half_w, half_h = w / 2.0, h / 2.0
        norm_x = (pt.x() - half_w) / half_w
        norm_y = (pt.y() - half_h) / half_h
        self.depth_brushed.emit(norm_x, norm_y)

    def paintGL(self):
        if self.mesh is not None and self.positions_2d is not None and self.rotated_3d is not None:
            self.renderer.render(
                mesh=self.mesh,
                positions_2d=self.positions_2d,
                rotated_3d=self.rotated_3d,
                view_size=(self.width(), self.height()),
                view_mode=self.view_mode
            )
