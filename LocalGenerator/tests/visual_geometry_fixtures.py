"""Explicit hand-authored presentation controls for current Visual inputs."""

def segment_geometry():
    return {"schema": "infini.body-geometry.v1", "source": "body_segment",
            "lengthPx": 40, "widthPx": 3, "axis": "rotation",
            "color": "#D2A345", "opacity": .8}

def collision_geometry():
    return {"schema": "infini.body-geometry.v1", "source": "collision_path",
            "widthPx": 3, "color": "#D2A345", "opacity": .8}
