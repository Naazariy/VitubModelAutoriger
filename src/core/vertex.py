import numpy as np
from dataclasses import dataclass, field
from typing import Tuple

@dataclass
class Vertex:
    """
    Represents a single vertex in the 2.5D mesh with geometric and physical properties.
    """
    position: np.ndarray          # 2D coordinate [x, y] in range [-1, 1] or pixel space
    normal: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 1.0], dtype=np.float64)) # 3D unit normal vector
    depth: float = 0.0            # Depth z value (relative to head center)
    stiffness: float = 0.5        # Stiffness coefficient [0, 1] (resistance to spring deformation)
    weight: float = 1.0           # Deformation influence weight [0, 1]
    layer_id: str = "Head"        # Semantic region ('Head', 'Face', 'Hair', 'Eyes', 'Accessories')
    index: int = -1               # Optional vertex index in mesh

    def copy(self) -> 'Vertex':
        return Vertex(
            position=np.array(self.position, dtype=np.float64).copy(),
            normal=np.array(self.normal, dtype=np.float64).copy(),
            depth=float(self.depth),
            stiffness=float(self.stiffness),
            weight=float(self.weight),
            layer_id=str(self.layer_id),
            index=int(self.index)
        )


@dataclass
class Triangle:
    """
    Represents a triangular face defined by three vertex indices.
    """
    v0: int
    v1: int
    v2: int

    @property
    def indices(self) -> Tuple[int, int, int]:
        return (int(self.v0), int(self.v1), int(self.v2))

    def signed_area(self, positions: np.ndarray) -> float:
        """
        Computes 2D signed area for this triangle given a vertex positions array.
        Positive indicates Counter-Clockwise (CCW) winding.
        """
        p0 = positions[self.v0]
        p1 = positions[self.v1]
        p2 = positions[self.v2]
        return 0.5 * float((p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1]))


@dataclass
class UV:
    """
    Represents texture coordinates (u, v) normalized in [0.0, 1.0].
    """
    u: float
    v: float

    @property
    def array(self) -> np.ndarray:
        return np.array([float(self.u), float(self.v)], dtype=np.float32)

