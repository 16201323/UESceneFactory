"""测试: SceneParseWorker 异步解析场景文件, 通过信号返回结果。"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_parse_worker_success():
    """验证 SceneParseWorker 能异步解析合法 JSON 并通过信号返回 (scene, info)。"""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QEventLoop, QTimer
    app = QApplication.instance() or QApplication(sys.argv)

    # 写一个合法场景 JSON 到临时文件
    scene_data = {
        "scene": {"name": "TestScene", "target_level": "/Game/Maps/Test"},
        "placements": [{"asset": "/Game/A", "location": [0, 0, 0]}],
    }
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(scene_data, tmp)
    tmp.close()

    from scripts.mapforge_app import SceneParseWorker
    worker = SceneParseWorker(tmp.name)
    results = {}
    def on_done(scene, info):
        results["scene"] = scene
        results["info"] = info
    worker.finished_signal.connect(on_done)
    worker.start()

    # 等待 worker 完成 (事件循环驱动)
    loop = QEventLoop()
    worker.finished_signal.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)  # 超时保护
    loop.exec()

    assert results.get("scene") is not None, "scene 未返回"
    assert results["info"]["name"] == "TestScene"
    assert results["info"]["total_actors"] == 1
    os.unlink(tmp.name)
    print("SceneParseWorker 成功解析验证通过")

def test_parse_worker_error():
    """验证非法文件路径时返回 (None, error_msg)。"""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QEventLoop, QTimer
    app = QApplication.instance() or QApplication(sys.argv)

    from scripts.mapforge_app import SceneParseWorker
    worker = SceneParseWorker("/nonexistent/path.json")
    results = {}
    def on_done(scene, info):
        results["scene"] = scene
        results["info"] = info
    worker.finished_signal.connect(on_done)
    worker.start()

    loop = QEventLoop()
    worker.finished_signal.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    assert results.get("scene") is None, "非法路径应返回 None"
    assert isinstance(results.get("info"), str), "应返回错误信息字符串"
    print("SceneParseWorker 错误处理验证通过")

def test_parse_scene_file_null_grid():
    """验证含 null grid 的 JSON 不崩溃 (pydantic model_dump_json 默认含 None 字段)。

    触发场景: Agent 管线通过 SceneJSON.model_dump_json() 序列化时,
    static 类型的 PlacementConfig.grid 字段为 None, 默认输出 "grid": null。
    parse_scene_file 遇到 "grid" in p 为 True 但 p["grid"] 为 None,
    对 None 调用 .get() 会抛 'NoneType' object has no attribute 'get'。
    """
    import json as _json, tempfile, os
    from scripts.mapforge_app import parse_scene_file

    # 模拟 pydantic model_dump_json 输出: static 类型含 "grid": null
    scene_data = {
        "scene": {"name": "NullGridTest", "target_level": "/Game/Maps/Test"},
        "placements": [
            {"type": "static", "asset": "/Game/A", "grid": None, "instances": None},
            {"type": "instanced_grid", "asset": "/Game/B",
             "grid": {"rows": 3, "cols": 4}},
        ],
    }
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8")
    _json.dump(scene_data, tmp)
    tmp.close()

    scene, info = parse_scene_file(tmp.name)
    os.unlink(tmp.name)

    assert scene is not None, "scene 不应为 None"
    assert info["name"] == "NullGridTest"
    # null grid 按 1 个 actor 计, 正常 grid 按 rows*cols=12 计 → 合计 13
    assert info["total_actors"] == 13, f"期望 13, 实际 {info['total_actors']}"
    print("parse_scene_file null grid 验证通过")

def test_parse_scene_file_null_root():
    """验证 JSON 根为 null 时不崩溃, 返回友好错误信息。"""
    import tempfile, os
    from scripts.mapforge_app import parse_scene_file

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8")
    tmp.write("null")
    tmp.close()

    scene, info = parse_scene_file(tmp.name)
    os.unlink(tmp.name)

    assert scene is None, "null 根应返回 None scene"
    assert isinstance(info, str), "应返回错误信息字符串"
    print("parse_scene_file null root 验证通过")

if __name__ == "__main__":
    test_parse_worker_success()
    test_parse_worker_error()
    test_parse_scene_file_null_grid()
    test_parse_scene_file_null_root()
    print("=== SceneParseWorker 测试通过 ===")
