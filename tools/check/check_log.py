"""检查最新的引擎日志"""
import re, os, glob, datetime

log_dir = r"D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Saved\Logs"
logs = [(f, os.path.getmtime(os.path.join(log_dir, f))) for f in os.listdir(log_dir) if f.startswith("MyUETest5_8_2")]
logs.sort(key=lambda x: x[1], reverse=True)
for name, mtime in logs:
    dt = datetime.datetime.fromtimestamp(mtime)
    size = os.path.getsize(os.path.join(log_dir, name))
    print(f"{dt.strftime('%H:%M:%S')}  {size:>10d}  {name}")

main_log = os.path.join(log_dir, "MyUETest5_8_2.log")
if os.path.exists(main_log):
    print(f"\n=== Main log ({os.path.getsize(main_log)} bytes) ===")
    with open(main_log, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    cmd_lines = re.findall(r"Cmd:.*", content)
    print(f"Cmd: lines: {len(cmd_lines)}")
    for l in cmd_lines[:10]:
        print(f"  {l[:300]}")
    for line in content.split("\n"):
        if "Command Line" in line or "commandline" in line.lower():
            print(f"CL: {line[:300]}")