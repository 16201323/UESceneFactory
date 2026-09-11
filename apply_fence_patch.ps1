# ASCII-only PowerShell script to insert section 8.3 (square fence) into SKILL.md
# Replaces the old "### 8.3 heading" with new 8.3 section + renumbered 8.4 heading
$skillPath = "c:\Users\25868\.trae-cn\skills\ue5_json\SKILL.md"
$patchPath = "c:\Users\25868\Desktop\UE5\MapForgeTest\skill_patch_fence.txt"
$backupPath = "c:\Users\25868\.trae-cn\skills\ue5_json\SKILL.md.bak2"
$oldHeading = "### 8.3 " + [char]0x6D3E + [char]0x751F + [char]0x8981 + [char]0x70B9
$utf8 = [System.Text.Encoding]::UTF8
$skillContent = [System.IO.File]::ReadAllText($skillPath, $utf8)
$patchContent = [System.IO.File]::ReadAllText($patchPath, $utf8)
$idx = $skillContent.IndexOf($oldHeading)
if ($idx -ge 0) {
    [System.IO.File]::WriteAllText($backupPath, $skillContent, $utf8)
    $newContent = $skillContent.Substring(0, $idx) + $patchContent + $skillContent.Substring($idx + $oldHeading.Length)
    [System.IO.File]::WriteAllText($skillPath, $newContent, $utf8)
    Write-Output "REPLACE_OK at index $idx"
    Write-Output ("OLD_LENGTH=" + $skillContent.Length)
    Write-Output ("NEW_LENGTH=" + $newContent.Length)
    Write-Output ("BACKUP_SAVED=" + $backupPath)
} else {
    Write-Output "MARKER_NOT_FOUND"
}
