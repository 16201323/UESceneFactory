import unreal

subsys = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
loc = unreal.Vector(12000, 44000, 9000)
rot = unreal.Rotator(-22, -38, 0)
subsys.set_level_viewport_camera_info(loc, rot)
print("CAMERA_NAV_DONE")
