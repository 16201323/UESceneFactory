import re
log_path = r'D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Saved\Logs\MyUETest5_8_2.log'
with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()
for keyword in ['SAVED', 'save_map', 'save_asset', 'save_all', 'SaveMap', 'ForceLayersFullUpdate', 'LandscapeHelper.*完成', 'Error.*save', 'Error.*Save']:
    lines = [l.strip() for l in content.split('\n') if keyword.lower() in l.lower()]
    if lines:
        print(f'=== Lines with "{keyword}" ({len(lines)}) ===')
        for l in lines[-15:]:
            print(f'  {l[:300]}')
        print()