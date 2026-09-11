import unreal
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
ues.set_level_viewport_camera_info(unreal.Vector(8000, -8000, 5000), unreal.Rotator(pitch=-25, yaw=45, roll=0))
if hasattr(ues, "set_level_viewport_fov"):
    ues.set_level_viewport_fov(90.0)
