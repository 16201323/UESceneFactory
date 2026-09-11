# ASCII-only: restore SKILL.md from backup, copy P1/P8 templates to skill folder, verify
$utf8 = [System.Text.Encoding]::UTF8

# Step 1: restore SKILL.md from backup (undo inline section 8)
$skillPath = "c:\Users\25868\.trae-cn\skills\ue5_json\SKILL.md"
$backupPath = "c:\Users\25868\.trae-cn\skills\ue5_json\SKILL.md.bak"
$backupContent = [System.IO.File]::ReadAllText($backupPath, $utf8)
[System.IO.File]::WriteAllText($skillPath, $backupContent, $utf8)
Write-Output ("RESTORE_OK length=" + $backupContent.Length)

# Step 2: create templates dir and copy P1/P8 JSON
$destDir = "c:\Users\25868\.trae-cn\skills\ue5_json\templates"
New-Item -ItemType Directory -Force -Path $destDir | Out-Null
Copy-Item "c:\Users\25868\Desktop\UE5\MapForgeTest\test_01_heliport.json" "$destDir\template_p1_heliport.json" -Force
Copy-Item "c:\Users\25868\Desktop\UE5\MapForgeTest\hv_tower_only.json" "$destDir\template_p8_hv_tower.json" -Force
Write-Output "COPY_OK"

# Step 3: verify copied files
$files = Get-ChildItem $destDir
foreach ($f in $files) {
    Write-Output ($f.Name + " " + $f.Length + "bytes")
}

# Step 4: verify SKILL.md no longer has inline section 8
$skillNow = [System.IO.File]::ReadAllText($skillPath, $utf8)
$hasSection8 = $skillNow.Contains("## 8. 完整场景模板")
Write-Output ("SKILL_HAS_INLINE_SECTION8=" + $hasSection8)
$hasMarker = $skillNow.Contains("## 示例 JSON 片段")
Write-Output ("SKILL_HAS_MARKER=" + $hasMarker)
