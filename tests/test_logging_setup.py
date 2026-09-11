"""测试: 持久化日志文件创建 + 崩溃捕获钩子安装。"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_log_dir_created():
    """验证日志目录在 APPDATA 下自动创建。"""
    # 模拟: 调用 _setup_logging 后应存在日志文件
    import mapforge_app
    # 日志目录应在 %APPDATA%/UESceneFactory/logs/ 或 ~/.uescenefactory/logs/
    log_dir = getattr(mapforge_app, '_LOG_DIR', None)
    assert log_dir is not None, '日志目录未设置'
    assert os.path.isdir(log_dir), f'日志目录不存在: {log_dir}'
    # 应至少有一个日志文件
    logs = [f for f in os.listdir(log_dir) if f.endswith('.log')]
    assert len(logs) > 0, f'日志目录无 .log 文件: {log_dir}'
    print(f'日志目录验证通过: {log_dir}, 文件: {logs}')

def test_excepthook_installed():
    """验证 sys.excepthook 已被替换为自定义钩子。"""
    import mapforge_app
    assert sys.excepthook is not sys.__excepthook__, 'sys.excepthook 未被替换'
    print('崩溃捕获钩子验证通过')

if __name__ == '__main__':
    test_log_dir_created()
    test_excepthook_installed()
    print('=== 日志系统测试通过 ===')
