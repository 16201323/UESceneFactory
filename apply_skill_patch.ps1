# ASCII-only PowerShell script to insert section 8 templates into SKILL.md
# Reads UTF-8 content files (patch + marker) and inserts before marker heading
$skillPath = "c:\Users\25868\.trae-cn\skills\ue5_json\SKILL.md"
$patchPath = "c:\Users\25868\Desktop\UE5\MapForgeTest\skill_patch.txt"
$markerPath = "c:\Users\25868\Desktop\UE5\MapForgeTest\skill_marker.txt"
$backupPath = "c:\Users\25868\.trae-cn\skills\ue5_json\SKILL.md.bak"
$utf8 = [System.Text.Encoding]::UTF8
$skillContent = [System.IO.File]::ReadAllText($skillPath, $utf8)
$patchContent = [System.IO.File]::ReadAllText($patchPath, $utf8)
$marker = [System.IO.File]::ReadAllText($markerPath, $utf8).Trim()
$idx = $skillContent.IndexOf($marker)
if ($idx -ge 0) {
    [System.IO.File]::WriteAllText($backupPath, $skillContent, $utf8)
    $newContent = $skillContent.Substring(0, $idx) + $patchContent + $skillContent.Substring($idx)
    [System.IO.File]::WriteAllText($skillPath, $newContent, $utf8)
    Write-Output "INSERT_OK at index $idx"
    Write-Output ("OLD_LENGTH=" + $skillContent.Length)
    Write-Output ("NEW_LENGTH=" + $newContent.Length)
    Write-Output ("BACKUP_SAVED=" + $backupPath)
} else {
    Write-Output "MARKER_NOT_FOUND"
    Write-Output ("MARKER=" + $marker)
}
