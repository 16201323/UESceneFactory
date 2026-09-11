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

if __name__ == "__main__":
    test_parse_worker_success()
    test_parse_worker_error()
    print("=== SceneParseWorker 测试通过 ===")
