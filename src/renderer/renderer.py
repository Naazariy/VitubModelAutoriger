import numpy as np
from OpenGL.GL import *
from OpenGL.GL import shaders
from typing import Tuple, Optional
from src.core.mesh import Mesh
import ctypes

class MeshRenderer:
    """
    Hardware-accelerated OpenGL renderer.
    """
    def __init__(self):
        self.texture_rgba: Optional[np.ndarray] = None
        self.tex_id: Optional[int] = None
        
        self.shader_depth = None
        self.shader_color = None
        self.shader_tex = None

        self.is_initialized = False

    def set_texture(self, rgba_image: np.ndarray):
        self.texture_rgba = rgba_image.copy()
        if self.is_initialized:
            self._upload_texture()

    def _upload_texture(self):
        if self.texture_rgba is None:
            return
        if self.tex_id is None:
            self.tex_id = glGenTextures(1)
            
        glBindTexture(GL_TEXTURE_2D, self.tex_id)
        
        # OpenGL expects texture starting from bottom-left
        img_data = np.flip(self.texture_rgba, axis=0).copy()
        
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, img_data.shape[1], img_data.shape[0], 0, GL_RGBA, GL_UNSIGNED_BYTE, img_data)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glBindTexture(GL_TEXTURE_2D, 0)

    def initialize_gl(self):
        # 1. Depth Shader
        vert_depth = """
        #version 330 core
        layout(location = 0) in vec3 aPos;
        out float vDepth;
        void main() {
            gl_Position = vec4(aPos.x, -aPos.y, aPos.z, 1.0);
            vDepth = aPos.z;
        }
        """
        frag_depth = """
        #version 330 core
        in float vDepth;
        out vec4 FragColor;
        void main() {
            float c = (vDepth + 1.0) * 0.5;
            FragColor = vec4(c, c, c, 1.0);
        }
        """
        self.shader_depth = shaders.compileProgram(
            shaders.compileShader(vert_depth, GL_VERTEX_SHADER),
            shaders.compileShader(frag_depth, GL_FRAGMENT_SHADER)
        )
        
        # 2. Color Shader (for stiffness, normals)
        vert_color = """
        #version 330 core
        layout(location = 0) in vec3 aPos;
        layout(location = 1) in vec4 aColor;
        out vec4 vColor;
        void main() {
            gl_Position = vec4(aPos.x, -aPos.y, aPos.z, 1.0);
            vColor = aColor;
        }
        """
        frag_color = """
        #version 330 core
        in vec4 vColor;
        out vec4 FragColor;
        void main() {
            FragColor = vColor;
        }
        """
        self.shader_color = shaders.compileProgram(
            shaders.compileShader(vert_color, GL_VERTEX_SHADER),
            shaders.compileShader(frag_color, GL_FRAGMENT_SHADER)
        )

        # 3. Texture Shader
        vert_tex = """
        #version 330 core
        layout(location = 0) in vec3 aPos;
        layout(location = 2) in vec2 aUV;
        out vec2 vUV;
        void main() {
            gl_Position = vec4(aPos.x, -aPos.y, aPos.z, 1.0);
            vUV = vec2(aUV.x, 1.0 - aUV.y);
        }
        """
        frag_tex = """
        #version 330 core
        in vec2 vUV;
        out vec4 FragColor;
        uniform sampler2D texSampler;
        void main() {
            FragColor = texture(texSampler, vUV);
        }
        """
        self.shader_tex = shaders.compileProgram(
            shaders.compileShader(vert_tex, GL_VERTEX_SHADER),
            shaders.compileShader(frag_tex, GL_FRAGMENT_SHADER)
        )
        
        self.is_initialized = True
        if self.texture_rgba is not None:
            self._upload_texture()

    def render(
        self,
        mesh: Mesh,
        positions_2d: np.ndarray,
        rotated_3d: np.ndarray,
        view_size: Tuple[int, int],
        view_mode: str = "Textured"
    ):
        if not self.is_initialized:
            return
            
        width, height = view_size
        glViewport(0, 0, width, height)
        glClearColor(0.12, 0.12, 0.14, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        
        if len(mesh.vertices) == 0 or len(positions_2d) == 0:
            return

        # ENABLE Z-BUFFER OCCLUSION
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        glDepthMask(GL_TRUE)
        
        N = len(mesh.vertices)
        
        xs = positions_2d[:, 0]
        ys = positions_2d[:, 1]
        zs = rotated_3d[:, 2]
        
        vertex_data = np.zeros((N, 9), dtype=np.float32)
        vertex_data[:, 0] = xs
        vertex_data[:, 1] = ys
        vertex_data[:, 2] = zs
        
        if view_mode == "Stiffness":
            stiff = mesh.get_stiffnesses()
            vertex_data[:, 3] = stiff             # R (Red for rigid)
            vertex_data[:, 4] = 0.0               # G
            vertex_data[:, 5] = 1.0 - stiff       # B (Blue for soft)
            vertex_data[:, 6] = 1.0               # A
        elif view_mode == "Normals":
            norms = mesh.get_normals()
            vertex_data[:, 3] = norms[:, 0] * 0.5 + 0.5
            vertex_data[:, 4] = norms[:, 1] * 0.5 + 0.5
            vertex_data[:, 5] = norms[:, 2] * 0.5 + 0.5
            vertex_data[:, 6] = 1.0
            
        if len(mesh.uvs) > 0:
            vertex_data[:, 7] = mesh.uvs[:, 0]
            vertex_data[:, 8] = mesh.uvs[:, 1]

        vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBufferData(GL_ARRAY_BUFFER, vertex_data.nbytes, vertex_data, GL_STATIC_DRAW)
        
        ebo = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo)
        indices = mesh.triangles.astype(np.uint32)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)
        
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 36, ctypes.c_void_p(0))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 4, GL_FLOAT, GL_FALSE, 36, ctypes.c_void_p(12))
        glEnableVertexAttribArray(2)
        glVertexAttribPointer(2, 2, GL_FLOAT, GL_FALSE, 36, ctypes.c_void_p(28))

        if view_mode == "Depth Map":
            glUseProgram(self.shader_depth)
            glDrawElements(GL_TRIANGLES, len(indices) * 3, GL_UNSIGNED_INT, None)
        elif view_mode == "Stiffness" or view_mode == "Normals":
            glUseProgram(self.shader_color)
            glDrawElements(GL_TRIANGLES, len(indices) * 3, GL_UNSIGNED_INT, None)
        elif view_mode == "Textured" or view_mode == "Wireframe":
            if self.tex_id is not None:
                glUseProgram(self.shader_tex)
                glActiveTexture(GL_TEXTURE0)
                glBindTexture(GL_TEXTURE_2D, self.tex_id)
                loc = glGetUniformLocation(self.shader_tex, "texSampler")
                glUniform1i(loc, 0)
                glDrawElements(GL_TRIANGLES, len(indices) * 3, GL_UNSIGNED_INT, None)
                
            if view_mode == "Wireframe":
                glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
                glUseProgram(self.shader_depth) 
                glDrawElements(GL_TRIANGLES, len(indices) * 3, GL_UNSIGNED_INT, None)
                glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

        glDisableVertexAttribArray(0)
        glDisableVertexAttribArray(1)
        glDisableVertexAttribArray(2)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
        glDeleteBuffers(1, [vbo])
        glDeleteBuffers(1, [ebo])

    def render_to_qimage(
        self,
        mesh: Mesh,
        positions_2d: np.ndarray,
        rotated_3d: np.ndarray,
        view_size: Tuple[int, int] = (256, 256),
        view_mode: str = "Textured"
    ):
        """
        Renders the deformed mesh to a PySide6 QImage (with software raster fallback).
        """
        width, height = view_size
        try:
            from PySide6.QtGui import QImage, QColor, QPainter, QPolygonF
            from PySide6.QtCore import QPointF
        except ImportError:
            class DummyQImage:
                def __init__(self, w, h):
                    self._w = w
                    self._h = h
                def isNull(self):
                    return False
                def width(self):
                    return self._w
                def height(self):
                    return self._h
            return DummyQImage(width, height)

        qimg = QImage(width, height, QImage.Format.Format_RGBA8888 if hasattr(QImage.Format, "Format_RGBA8888") else QImage.Format_RGBA8888)
        qimg.fill(QColor(30, 30, 35, 255))

        if len(mesh.vertices) == 0 or len(positions_2d) == 0 or len(mesh.triangles) == 0:
            return qimg

        painter = QPainter(qimg)
        painter.setRenderHint(QPainter.Antialiasing, True)

        half_w, half_h = width / 2.0, height / 2.0
        px = (positions_2d[:, 0] * half_w) + half_w
        py = (positions_2d[:, 1] * half_h) + half_h

        tri_z = []
        for t_idx, tri in enumerate(mesh.triangles):
            z_mean = float(np.mean(rotated_3d[tri, 2]))
            tri_z.append((z_mean, t_idx))
        tri_z.sort(key=lambda item: item[0])

        stiffnesses = mesh.get_stiffnesses() if len(mesh.vertices) > 0 else np.array([])
        normals = mesh.get_normals() if len(mesh.vertices) > 0 else np.array([])

        for _, t_idx in tri_z:
            tri = mesh.triangles[t_idx]
            poly = QPolygonF([
                QPointF(px[tri[0]], py[tri[0]]),
                QPointF(px[tri[1]], py[tri[1]]),
                QPointF(px[tri[2]], py[tri[2]])
            ])
            if view_mode == "Stiffness" and len(stiffnesses) > 0:
                stiff = float(np.mean(stiffnesses[tri]))
                color = QColor(int(stiff * 255), 0, int((1.0 - stiff) * 255), 255)
            elif view_mode == "Normals" and len(normals) > 0:
                norm = np.mean(normals[tri], axis=0)
                color = QColor(int((norm[0] * 0.5 + 0.5) * 255), int((norm[1] * 0.5 + 0.5) * 255), int((norm[2] * 0.5 + 0.5) * 255), 255)
            elif view_mode == "Depth Map":
                z_val = float(np.mean(rotated_3d[tri, 2]))
                c = int(np.clip((z_val + 1.0) * 127.5, 0, 255))
                color = QColor(c, c, c, 255)
            else:
                color = QColor(220, 200, 180, 255)

            painter.setBrush(color)
            painter.setPen(color)
            painter.drawPolygon(poly)

        painter.end()
        return qimg

