import sys
import numpy as np
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSlider,
    QLabel, QComboBox, QPushButton, QFileDialog, QGroupBox, QCheckBox, QMessageBox
)
from PySide6.QtCore import Qt
from typing import Optional

from src.importer.image_importer import ImageImporter
from src.generator.mesh_generator import MeshGenerator
from src.depth.depth_model import DepthModel
from src.geometry.geometry_engine import GeometryEngine
from src.deformation.deformation_solver import DeformationSolver
from src.constraints.constraint_solver import MassSpringConstraintSolver
from src.ai.ai_assistant import AIAssistant
from src.gui.viewport import ViewportWidget
from src.core.mesh import Mesh

class MainWindow(QMainWindow):
    """
    Main PySide6 Desktop GUI Window for real-time 2.5D keyframe-free head deformation prototype.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live2D Geometry Deformation Prototype (Keyframe-Free)")
        self.resize(1000, 700)

        # Core pipeline instances
        self.depth_model = DepthModel()
        self.deformation_solver = DeformationSolver()
        self.constraint_solver = MassSpringConstraintSolver()

        self.rgba_image: Optional[np.ndarray] = None
        self.alpha_mask: Optional[np.ndarray] = None
        self.mesh: Optional[Mesh] = None

        self._init_ui()
        self.load_synthetic_character()

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # --- Viewport Canvas ---
        self.viewport = ViewportWidget()
        self.viewport.depth_brushed.connect(self.on_depth_brushed)
        main_layout.addWidget(self.viewport, stretch=3)

        # --- Sidebar Controls ---
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        main_layout.addWidget(sidebar, stretch=1)

        # 1. Image & Mesh Controls
        group_import = QGroupBox("1. Model & Mesh")
        layout_import = QVBoxLayout(group_import)
        
        btn_synthetic = QPushButton("Load Synthetic Head")
        btn_synthetic.clicked.connect(self.load_synthetic_character)
        layout_import.addWidget(btn_synthetic)

        btn_import_png = QPushButton("Import PNG Image...")
        btn_import_png.clicked.connect(self.import_png_file)
        layout_import.addWidget(btn_import_png)

        sidebar_layout.addWidget(group_import)

        # 2. Deformation Controls (AngleX, AngleY)
        group_deform = QGroupBox("2. Real-Time Head Rotation")
        layout_deform = QVBoxLayout(group_deform)

        # AngleX Slider
        layout_deform.addWidget(QLabel("AngleX (Yaw: -30° to +30°):"))
        self.lbl_anglex = QLabel("0.0°")
        layout_deform.addWidget(self.lbl_anglex)
        self.slider_anglex = QSlider(Qt.Horizontal)
        self.slider_anglex.setRange(-30, 30)
        self.slider_anglex.setValue(0)
        self.slider_anglex.valueChanged.connect(self.update_deformation)
        layout_deform.addWidget(self.slider_anglex)

        # AngleY Slider
        layout_deform.addWidget(QLabel("AngleY (Pitch: -30° to +30°):"))
        self.lbl_angley = QLabel("0.0°")
        layout_deform.addWidget(self.lbl_angley)
        self.slider_angley = QSlider(Qt.Horizontal)
        self.slider_angley.setRange(-30, 30)
        self.slider_angley.setValue(0)
        self.slider_angley.valueChanged.connect(self.update_deformation)
        layout_deform.addWidget(self.slider_angley)

        btn_reset_angles = QPushButton("Reset Angles (0°, 0°)")
        btn_reset_angles.clicked.connect(self.reset_angles)
        layout_deform.addWidget(btn_reset_angles)

        sidebar_layout.addWidget(group_deform)

        # 3. View Mode & Visualization
        group_view = QGroupBox("3. View Mode & Tools")
        layout_view = QVBoxLayout(group_view)

        layout_view.addWidget(QLabel("Render View Mode:"))
        self.combo_view_mode = QComboBox()
        self.combo_view_mode.addItems(["Textured", "Wireframe", "Depth Map", "Normals", "Stiffness"])
        self.combo_view_mode.currentTextChanged.connect(self.update_deformation)
        layout_view.addWidget(self.combo_view_mode)

        self.chk_brush = QCheckBox("Enable Depth Paint Brush")
        self.chk_brush.toggled.connect(self.toggle_brush)
        layout_view.addWidget(self.chk_brush)

        btn_ai_auto = QPushButton("AI Auto Depth & Stiffness")
        btn_ai_auto.clicked.connect(self.apply_ai_auto)
        layout_view.addWidget(btn_ai_auto)

        sidebar_layout.addWidget(group_view)

        # 4. MVP Export Stub
        group_export = QGroupBox("4. Export / Save (MVP Stub)")
        layout_export = QVBoxLayout(group_export)
        btn_export_stub = QPushButton("Export .moc3 / Project (Stub)")
        btn_export_stub.clicked.connect(self.on_export_stub)
        layout_export.addWidget(btn_export_stub)

        sidebar_layout.addWidget(group_export)
        sidebar_layout.addStretch()

    def load_synthetic_character(self):
        self.rgba_image, self.alpha_mask = ImageImporter.create_synthetic_head_image(512, 512)
        self.setup_mesh_and_pipeline()

    def import_png_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open Character PNG", "", "PNG Images (*.png)")
        if filepath:
            self.rgba_image, self.alpha_mask = ImageImporter.load_image(filepath)
            self.setup_mesh_and_pipeline()

    def setup_mesh_and_pipeline(self):
        if self.rgba_image is None or self.alpha_mask is None:
            return

        contour_pts = ImageImporter.extract_contour(self.alpha_mask, threshold=10, simplify_eps=3.0)
        h, w, _ = self.rgba_image.shape
        self.mesh = MeshGenerator.generate_mesh_from_contour(contour_pts, (h, w), target_grid_size=30)
        
        # Apply depth & geometry normals
        self.depth_model.apply_ellipsoid_to_mesh(self.mesh)
        GeometryEngine.update_mesh_normals_and_geometry(
            self.mesh,
            ((self.depth_model.center_x, self.depth_model.center_y),
             (self.depth_model.radius_x, self.depth_model.radius_y, self.depth_model.radius_z))
        )

        # Auto estimate initial stiffness and depth refinements
        AIAssistant.auto_assign_mesh_properties(self.mesh, self.rgba_image, self.alpha_mask)

        # Update viewport texture
        self.viewport.set_texture(self.rgba_image)
        
        # Invalidate constraint solver cache for new mesh
        self.constraint_solver.initialize_sparse_system(self.mesh)
        
        self.update_deformation()

    def update_deformation(self):
        if self.mesh is None:
            return

        angle_x = float(self.slider_anglex.value())
        angle_y = float(self.slider_angley.value())

        self.lbl_anglex.setText(f"{angle_x:.1f}°")
        self.lbl_angley.setText(f"{angle_y:.1f}°")

        # 1. Deformation Solver (3D rotation + Parallax 2D projection + Rotated 3D coordinates for z-buffer)
        projected_2d, rotated_3d = self.deformation_solver.solve(self.mesh, angle_x, angle_y)

        # 2. Mass-Spring Constraint Solver (cached sparse matrix factorization)
        solved_2d, _ = self.constraint_solver.solve(self.mesh, projected_2d, num_iterations=3)

        # 3. Render in Viewport
        view_mode = self.combo_view_mode.currentText()
        self.viewport.update_render_data(self.mesh, solved_2d, rotated_3d, view_mode)

    def reset_angles(self):
        self.slider_anglex.setValue(0)
        self.slider_angley.setValue(0)

    def toggle_brush(self, enabled: bool):
        self.viewport.brush_active = enabled

    def on_depth_brushed(self, norm_x: float, norm_y: float):
        if self.mesh is not None and self.chk_brush.isChecked():
            self.depth_model.apply_depth_brush(self.mesh, (norm_x, norm_y), radius=0.25, intensity=0.08)
            GeometryEngine.update_mesh_normals_and_geometry(
                self.mesh,
                ((self.depth_model.center_x, self.depth_model.center_y),
                 (self.depth_model.radius_x, self.depth_model.radius_y, self.depth_model.radius_z))
            )
            self.update_deformation()

    def apply_ai_auto(self):
        if self.mesh is not None and self.rgba_image is not None and self.alpha_mask is not None:
            AIAssistant.auto_assign_mesh_properties(self.mesh, self.rgba_image, self.alpha_mask)
            GeometryEngine.update_mesh_normals_and_geometry(
                self.mesh,
                ((self.depth_model.center_x, self.depth_model.center_y),
                 (self.depth_model.radius_x, self.depth_model.radius_y, self.depth_model.radius_z))
            )
            self.update_deformation()

    def on_export_stub(self):
        QMessageBox.information(
            self,
            "MVP Validation Scope",
            "Export feature is marked as a stub ('not required for MVP validation').\n"
            "The current stage validates the mathematical deformation engine."
        )
