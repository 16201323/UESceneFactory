# -*- coding: utf-8 -*-
import unreal
import os
import traceback

LOG_PATH = "c:/Users/25868/Desktop/UE5/gen_shots_internal.log"
_f = open(LOG_PATH, "w", encoding="utf-8")

def log(msg):
    print(msg)
    _f.write(str(msg) + "\n")
    _f.flush()

SHOT_DIR = "c:/Users/25868/Desktop/UE5/screenshots"
ALLDONE_PATH = "c:/Users/25868/Desktop/UE5/gen_shots_internal_ALLDONE.txt"
ERROR_PATH = "c:/Users/25868/Desktop/UE5/gen_shots_internal_ERROR.txt"

SCENES = [
    ("/Game/MapForgeTest/GB_Test_01_Heliport",   (2500, -2500, 1800),  (-35, 45, 0), "01_heliport"),
    ("/Game/MapForgeTest/GB_Test_02_Wirefence",  (3500, -3500, 2500),  (-40, 45, 0), "02_wirefence"),
    ("/Game/MapForgeTest/GB_Test_03_Hangar",     (3500, -3500, 2000),  (-30, 45, 0), "03_hangar"),
    ("/Game/MapForgeTest/GB_Test_04_Charging",   (2000, -2000, 1200),  (-25, 45, 0), "04_charging"),
    ("/Game/MapForgeTest/GB_Test_05_Solar",      (2500, -2500, 1800),  (-35, 45, 0), "05_solar"),
    ("/Game/MapForgeTest/GB_Test_06_Trees",      (4500, -4500, 3000),  (-40, 45, 0), "06_trees"),
    ("/Game/MapForgeTest/GB_Test_07_CommTower",  (3500, -3500, 2500),  (-25, 45, 0), "07_comm_tower"),
    ("/Game/MapForgeTest/GB_Test_08_HVTower",     (8000, -8000, 9000),  (-30, 45, 0), "08_hv_tower"),
    ("/Game/MapForgeTest/GB_Test_09_Village",     (6000, -6000, 3500),  (-40, 45, 0), "09_village"),
    ("/Game/MapForgeTest/GB_Test_10_Forest",      (8000, -8000, 5000),  (-40, 45, 0), "10_forest"),
]

SETTLE_TICKS = 80
RENDER_WAIT_TICKS = 30
FILE_WAIT_TIMEOUT = 200
CLEANUP_TICKS = 3
GAP_TICKS = 30
FINAL_WAIT_TICKS = 200
MAX_PASSES = 2


class ShotController:
    def __init__(self):
        self.state = "INIT"
        self.scene_index = 0
        self.pass_number = 1
        self.tick_count = 0
        self.camera_actor = None
        self.expected_path = ""
        self.capture_task = None
        self.les = None
        self._handle = None

    def tick(self, delta):
        try:
            self._tick_impl(delta)
        except Exception as e:
            log(f"FATAL tick error: {e}")
            log(traceback.format_exc())
            try:
                unreal.unregister_slate_pre_tick_callback(self._handle)
            except:
                pass
            try:
                with open(ERROR_PATH, "w") as ef:
                    ef.write(f"FATAL: {e}\n{traceback.format_exc()}")
            except:
                pass

    def _tick_impl(self, delta):
        if self.state == "INIT":
            if os.path.isdir(SHOT_DIR):
                for fn in os.listdir(SHOT_DIR):
                    if fn.lower().endswith(".png"):
                        try:
                            os.remove(os.path.join(SHOT_DIR, fn))
                        except:
                            pass
            else:
                os.makedirs(SHOT_DIR, exist_ok=True)
            for p in [ALLDONE_PATH, ERROR_PATH]:
                if os.path.isfile(p):
                    try:
                        os.remove(p)
                    except:
                        pass
            self.les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            self.les.editor_set_viewport_realtime(True)
            try:
                self.les.editor_set_game_view(True)
                log("Game view enabled (hides editor UI)")
            except Exception as e:
                log(f"Game view enable failed: {e}")
            log("INIT complete, starting screenshots")
            self.state = "LOAD"
            self.tick_count = 0
            return

        if self.state == "LOAD":
            if self.scene_index >= len(SCENES):
                if self.pass_number < MAX_PASSES:
                    self.pass_number += 1
                    self.scene_index = 0
                    self.state = "GAP"
                    self.tick_count = 0
                    log(f"=== Starting Pass {self.pass_number} ===")
                    return
                else:
                    self.state = "FINAL_WAIT"
                    self.tick_count = 0
                    log("All passes done, entering FINAL_WAIT")
                    try:
                        unreal.EditorLevelLibrary.load_level(SCENES[0][0])
                    except:
                        pass
                    return

            level_path, cam_loc, cam_rot, name = SCENES[self.scene_index]
            self.expected_path = os.path.join(SHOT_DIR, f"shot_{name}.png")

            if self.pass_number == 2:
                if os.path.isfile(self.expected_path):
                    sz = os.path.getsize(self.expected_path)
                    if sz > 100:
                        log(f"Pass 2: {name} already has screenshot ({sz} bytes), skipping")
                        self.scene_index += 1
                        return

            log(f"=== Pass {self.pass_number} Scene {self.scene_index+1}/{len(SCENES)} ({name}) ===")
            log(f"Loading {level_path}")
            unreal.EditorLevelLibrary.load_level(level_path)
            self.state = "SETTLE"
            self.tick_count = 0
            return

        if self.state == "GAP":
            self.tick_count += 1
            if self.tick_count >= GAP_TICKS:
                log(f"Gap done ({GAP_TICKS} ticks)")
                self.state = "LOAD"
                self.tick_count = 0
            return

        if self.state == "SETTLE":
            self.tick_count += 1
            if self.tick_count >= SETTLE_TICKS:
                log(f"Settled ({SETTLE_TICKS} ticks)")
                self.state = "CAM"
                self.tick_count = 0
            return

        if self.state == "CAM":
            level_path, cam_loc, cam_rot, name = SCENES[self.scene_index]
            loc = unreal.Vector(cam_loc[0], cam_loc[1], cam_loc[2])
            rot = unreal.Rotator(pitch=cam_rot[0], yaw=cam_rot[1], roll=cam_rot[2])
            try:
                viewport_key = self.les.get_active_viewport_config_key()
                self.les.set_level_viewport_camera_info(loc, rot, viewport_key)
                self.les.editor_set_viewport_realtime(True)
                try:
                    self.les.set_level_viewport_fov(90.0, viewport_key)
                except:
                    pass
                log(f"Viewport camera set to {cam_loc} / {cam_rot}")
            except Exception as e:
                log(f"Viewport camera set failed: {e}")
            self.camera_actor = None
            try:
                self.camera_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
                    unreal.CameraActor, loc, rot
                )
                log("Camera actor spawned")
            except Exception as e:
                log(f"Spawn camera failed: {e}")
            self.state = "RENDER_WAIT"
            self.tick_count = 0
            return

        if self.state == "RENDER_WAIT":
            self.tick_count += 1
            if self.tick_count >= RENDER_WAIT_TICKS:
                log(f"Render wait done ({RENDER_WAIT_TICKS} ticks)")
                self.state = "SHOT"
                self.tick_count = 0
            return

        if self.state == "SHOT":
            self.state = "FILE_WAIT"
            self.tick_count = 0
            self.capture_task = None
            level_path, cam_loc, cam_rot, name = SCENES[self.scene_index]
            log(f"Taking screenshot -> {self.expected_path}")
            if self.camera_actor:
                try:
                    self.capture_task = unreal.AutomationLibrary.take_high_res_screenshot(
                        1920, 1080, self.expected_path,
                        camera=self.camera_actor, delay=0.25
                    )
                    if self.capture_task and self.capture_task.is_valid_task():
                        log("Task created (camera + delay=0.25)")
                        return
                except Exception as e:
                    log(f"take_high_res_screenshot(camera+delay) failed: {e}")
            if self.camera_actor:
                try:
                    self.capture_task = unreal.AutomationLibrary.take_high_res_screenshot(
                        1920, 1080, self.expected_path,
                        camera=self.camera_actor
                    )
                    if self.capture_task and self.capture_task.is_valid_task():
                        log("Task created (camera, no delay)")
                        return
                except Exception as e:
                    log(f"take_high_res_screenshot(camera) failed: {e}")
            try:
                self.capture_task = unreal.AutomationLibrary.take_high_res_screenshot(
                    1920, 1080, self.expected_path
                )
                if self.capture_task and self.capture_task.is_valid_task():
                    log("Task created (viewport, no camera)")
                else:
                    log("WARNING: No valid task created")
            except Exception as e:
                log(f"take_high_res_screenshot(viewport) failed: {e}")
            return

        if self.state == "FILE_WAIT":
            self.tick_count += 1
            if self.capture_task and self.capture_task.is_valid_task():
                try:
                    if self.capture_task.is_task_done():
                        log(f"Task done after {self.tick_count} ticks")
                        self.state = "CLEANUP"
                        self.tick_count = 0
                        return
                except Exception as e:
                    log(f"is_task_done() check failed: {e}")
            if self.tick_count % 10 == 0:
                if os.path.isfile(self.expected_path):
                    sz = os.path.getsize(self.expected_path)
                    if sz > 100:
                        log(f"Screenshot saved -> {self.expected_path} ({sz} bytes)")
                        self.state = "CLEANUP"
                        self.tick_count = 0
                        return
            if self.tick_count >= FILE_WAIT_TIMEOUT:
                log(f"File wait timeout ({FILE_WAIT_TIMEOUT} ticks), moving on")
                self.state = "CLEANUP"
                self.tick_count = 0
            return

        if self.state == "CLEANUP":
            self.tick_count += 1
            if self.tick_count >= CLEANUP_TICKS:
                if self.camera_actor:
                    try:
                        unreal.EditorLevelLibrary.destroy_actor(self.camera_actor)
                    except:
                        try:
                            self.camera_actor.destroy_actor()
                        except:
                            pass
                    self.camera_actor = None
                level_path, cam_loc, cam_rot, name = SCENES[self.scene_index]
                log(f"Scene {self.scene_index+1} ({name}): cleanup done")
                self.scene_index += 1
                self.state = "LOAD"
                self.tick_count = 0
            return

        if self.state == "FINAL_WAIT":
            self.tick_count += 1
            if self.tick_count % 10 == 0:
                last_name = SCENES[-1][3]
                last_path = os.path.join(SHOT_DIR, f"shot_{last_name}.png")
                if os.path.isfile(last_path):
                    sz = os.path.getsize(last_path)
                    if sz > 100:
                        log(f"Last screenshot confirmed: {last_path} ({sz} bytes)")
                        self.state = "DONE"
                        self.tick_count = 0
                        return
            if self.tick_count >= FINAL_WAIT_TICKS:
                log(f"Final wait done ({FINAL_WAIT_TICKS} ticks)")
                self.state = "DONE"
                self.tick_count = 0
            return

        if self.state == "DONE":
            log("=== ALL scenes done! ===")
            for level_path, cam_loc, cam_rot, name in SCENES:
                p = os.path.join(SHOT_DIR, f"shot_{name}.png")
                if os.path.isfile(p):
                    log(f"  {name}: {os.path.getsize(p)} bytes OK")
                else:
                    log(f"  {name}: MISSING!")
            try:
                self.les.editor_set_game_view(False)
                log("Game view disabled")
            except:
                pass
            try:
                with open(ALLDONE_PATH, "w") as af:
                    af.write("done")
                log("ALLDONE signal written")
            except:
                pass
            try:
                unreal.unregister_slate_pre_tick_callback(self._handle)
                log("Callback unregistered")
            except:
                pass
            return

log("=== gen_shots_internal.py started (pre-tick, is_task_done, game_view, 2-pass) ===")
log(f"Total scenes: {len(SCENES)}, max passes: {MAX_PASSES}")

controller = ShotController()
controller._handle = unreal.register_slate_pre_tick_callback(controller.tick)
log("ShotController started, waiting for editor pre-ticks...")
