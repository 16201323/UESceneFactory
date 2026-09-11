import unreal

unreal.log("PY_OK_5_8_TEST")

actor = unreal.EditorLevelLibrary.get_actor_by_name('GB_Cube_Red')
if actor:
    unreal.log("ACTOR_FOUND: " + actor.get_name())
else:
    unreal.log("ACTOR_NOT_FOUND")

actors = unreal.EditorLevelLibrary.get_all_level_actors()
unreal.log("ACTOR_COUNT: " + str(len(actors)))
for a in actors:
    unreal.log("  - " + a.get_name())
