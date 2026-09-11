import unreal, os, traceback

LOG_PATH = "c:/Users/25868/Desktop/UE5/gen_shots_tick.log"
_f = open(LOG_PATH, "w", encoding="utf-8")
def log(msg):
    print(msg)
    _f.write(str(msg) + "\n")
    _f.flush()

SIGNAL_DIR = "c:/Users/25868/Desktop/UE5/MapForgeTest/signals"

SCENES = [
    ("/Game/MapForgeTest/GB_Test_01_Heliport",   (2500, -2500, 1800),  (-35, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_02_Wirefence",  (3500, -3500, 2500),  (-40, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_03_Hangar",     (3500, -3500, 2000),  (-30, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_04_Charging",   (2000, -2000, 1200),  (-25, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_05_Solar",      (2500, -2500, 1800),  (-35, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_06_Trees",       (4500, -4500, 3000),  (-40, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_07_CommTower",  (3500, -3500, 2500),  (-25, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_08_HVTower",     (8000, -8000, 9000),  (-30, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_09_Village",     (6000, -6000, 3500),  (-40, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_10_Forest",      (8000, -8000, 5000),  (-40, 45, 0)),
]

class ShotController:
    def __init__(self):
        self.state = "INIT"
        self.index = 0
        self.tick_count = 0
        self.handle = None
        self.go_timeout = 0

    def set_camera(self, loc_tuple, rot_tuple):
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        new_loc = unreal.Vector(loc_tuple[0], loc_tuple[1], loc_tuple[2])
        new_rot = unreal.Rotator(pitch=rot_tuple[0], yaw=rot_tuple[1], roll=rot_tuple[2])
        viewport_key = les.get_active_viewport_config_key()
        les.set_level_viewport_camera_info(new_loc, new_rot, viewport_key)
        try: les.editor_set_viewport_realtime(True)
        except: pass
        try: les.editor_invalidate_viewports()
        except: pass
        try: les.set_level_viewport_fov(90.0, viewport_key)
        except: pass

    def write_signal(self, name):
        path = os.path.join(SIGNAL_DIR, name)
        with open(path, "w") as f:
            f.write("ok")

    def check_signal(self, name):
        path = os.path.join(SIGNAL_DIR, name)
        return os.path.isfile(path)

    def cleanup(self):
        if os.path.isdir(SIGNAL_DIR):
            for f in os.listdir(SIGNAL_DIR):
                try: os.remove(os.path.join(SIGNAL_DIR, f))
                except: pass
        else:
            os.makedirs(SIGNAL_DIR, exist_ok=True)

    def unregister(self):
        if self.handle is not None:
            try: unreal.unregister_slate_post_tick_callback(self.handle)
            except: pass
            self.handle = None

    def tick(self, delta):
        self.tick_count += 1
        try:
            if self.state == "INIT":
                self.cleanup()
                log("INIT done, starting scene loading")
                self.state = "LOAD"
                self.tick_count = 0

            elif self.state == "LOAD":
                level_path, cam_loc, cam_rot = SCENES[self.index]
                log(f"Scene {self.index+1}: Loading {level_path}")
                unreal.EditorLevelLibrary.load_level(level_path)
                log(f"Scene {self.index+1}: Level loaded")
                self.state = "SETTLE"
                self.tick_count = 0

            elif self.state == "SETTLE":
                if self.tick_count > 30:
                    log(f"Scene {self.index+1}: Settled ({self.tick_count} ticks)")
                    self.state = "CAMERA"
                    self.tick_count = 0

            elif self.state == "CAMERA":
                level_path, cam_loc, cam_rot = SCENES[self.index]
                self.set_camera(cam_loc, cam_rot)
                log(f"Scene {self.index+1}: Camera set to {cam_loc} / {cam_rot}")
                self.state = "RENDER"
                self.tick_count = 0

            elif self.state == "RENDER":
                if self.tick_count > 120:
                    log(f"Scene {self.index+1}: Rendered ({self.tick_count} ticks), writing READY_{self.index+1}")
                    self.write_signal(f"READY_{self.index+1}.txt")
                    self.state = "WAIT_GO"
                    self.tick_count = 0
                    self.go_timeout = 0

            elif self.state == "WAIT_GO":
                if self.check_signal(f"GO_{self.index+1}.txt"):
                    log(f"Scene {self.index+1}: GO received, moving to next")
                    try: os.remove(os.path.join(SIGNAL_DIR, f"GO_{self.index+1}.txt"))
                    except: pass
                    self.index += 1
                    if self.index >= len(SCENES):
                        log("ALL scenes done! Writing ALL_DONE")
                        self.write_signal("ALL_DONE.txt")
                        self.unregister()
                        log("Slate post-tick callback unregistered")
                    else:
                        self.state = "LOAD"
                        self.tick_count = 0
                else:
                    self.go_timeout += 1
                    if self.go_timeout > 18000:
                        log(f"Scene {self.index+1}: GO timeout (5 min)!")
                        self.write_signal("ALL_DONE.txt")
                        self.unregister()
                        log("Slate post-tick callback unregistered (timeout)")

        except Exception as e:
            log(f"ERROR in state {self.state}: {e}")
            log(traceback.format_exc())
            self.write_signal("ALL_DONE.txt")
            self.unregister()

controller = ShotController()
controller.handle = unreal.register_slate_post_tick_callback(controller.tick)
log(f"Slate post-tick callback registered, handle={controller.handle}")
log(f"Total scenes: {len(SCENES)}")
