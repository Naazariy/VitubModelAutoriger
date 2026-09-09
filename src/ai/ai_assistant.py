import cv2
import numpy as np
from src.core.mesh import Mesh

class AIAssistant:
    """
    AI / Heuristic Assistant module to help users auto-calculate geometric properties:
    - Auto depth map estimation from silhouette distance transform
    - Auto normal map derivation
    - Auto stiffness map estimation based on edge density
    - Auto semantic region tagging
    """
    @staticmethod
    def auto_estimate_depth_map(alpha_mask: np.ndarray) -> np.ndarray:
        """
        Estimates depth map from character silhouette using distance transform and radial blending.
        Returns:
            depth_map: np.ndarray of shape (H, W) in float64 range [0, 1]
        """
        _, binary = cv2.threshold(alpha_mask, 10, 255, cv2.THRESH_BINARY)
        dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
        
        max_dist = np.max(dist)
        if max_dist > 0:
            depth_map = dist / max_dist
        else:
            depth_map = np.zeros_like(alpha_mask, dtype=np.float64)
            
        # Apply smooth Gaussian blur
        depth_map = cv2.GaussianBlur(depth_map, (15, 15), 0)
        return depth_map

    @staticmethod
    def auto_estimate_stiffness_map(rgba_image: np.ndarray, alpha_mask: np.ndarray) -> np.ndarray:
        """
        Estimates vertex stiffness map based on edge density with smooth gradient falloff.
        Rigid areas (eyes/mouth): ~1.0
        Soft areas (cheeks/skin): ~0.2 - 0.4
        """
        gray = cv2.cvtColor(rgba_image, cv2.COLOR_RGBA2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        
        # Dilate edge map for initial rigid region influence
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
        rigid_mask = cv2.dilate(edges.astype(np.float32) / 255.0, kernel)
        
        # Apply large-kernel Gaussian blur for spatial smoothing / gradient falloff
        smoothed_rigid = cv2.GaussianBlur(rigid_mask, (45, 45), 0)
        
        # Base stiffness: 0.25 for soft skin, up to 1.0 for rigid feature edges
        stiffness_map = 0.25 + 0.75 * smoothed_rigid
        
        # Enforce strict bounds S_i in [0, 1]
        stiffness_map = np.clip(stiffness_map, 0.0, 1.0)
        
        # Mask out transparent background
        stiffness_map[alpha_mask < 10] = 0.0
        return stiffness_map

    @staticmethod
    def auto_assign_mesh_properties(mesh: Mesh, rgba_image: np.ndarray, alpha_mask: np.ndarray):
        """
        Applies auto-estimated depth and stiffness maps onto mesh vertices.
        """
        h, w = alpha_mask.shape
        depth_map = AIAssistant.auto_estimate_depth_map(alpha_mask)
        stiffness_map = AIAssistant.auto_estimate_stiffness_map(rgba_image, alpha_mask)

        half_w, half_h = w / 2.0, h / 2.0

        for vtx in mesh.vertices:
            # Map vertex position [-1, 1] back to pixel coordinates
            px = int(np.clip((vtx.position[0] * half_w) + half_w, 0, w - 1))
            py = int(np.clip((vtx.position[1] * half_h) + half_h, 0, h - 1))

            vtx.depth = float(depth_map[py, px] * 0.4)  # Scale depth to match head radius Z
            vtx.stiffness = float(stiffness_map[py, px])

            # Heuristic layer region tagging based on relative position
            rel_y = vtx.position[1]
            rel_x = vtx.position[0]
            if rel_y < -0.4:
                vtx.layer_id = "Hair"
            elif abs(rel_x) > 0.5 and abs(rel_y) < 0.2:
                vtx.layer_id = "Accessories"
            elif abs(rel_y) < 0.2 and abs(rel_x) < 0.35:
                vtx.layer_id = "Eyes"
            else:
                vtx.layer_id = "Head"
