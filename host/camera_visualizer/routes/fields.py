"""Field model and AprilTag routes."""


def get_field_tags() -> dict:
    """Get AprilTag positions from robotpy_apriltag field layout."""
    try:
        from robotpy_apriltag import AprilTagField, AprilTagFieldLayout
        layout = AprilTagFieldLayout.loadField(AprilTagField.kDefaultField)
        tags = []
        for tag_id in range(1, 50):
            pose = layout.getTagPose(tag_id)
            if pose is None:
                continue
            t = pose.translation()
            r = pose.rotation()
            tags.append({
                'id': tag_id,
                'x': round(t.X(), 4),
                'y': round(t.Y(), 4),
                'z': round(t.Z(), 4),
                'roll_deg': round(r.x_degrees, 1),
                'pitch_deg': round(r.y_degrees, 1),
                'yaw_deg': round(r.z_degrees, 1),
            })
        return {
            'field_length': round(layout.getFieldLength(), 4),
            'field_width': round(layout.getFieldWidth(), 4),
            'tags': tags,
        }
    except Exception as e:
        return {'error': str(e), 'tags': []}
