# ASCII-only PowerShell: insert section 8.4 (P5 PV template) into SKILL.md
# Replace "### 8.4 <CJK>" with patch content that ends with "### 8.5 <CJK>"
$skillPath = "c:\Users\25868\.trae-cn\skills\ue5_json\SKILL.md"
$patchPath = "c:\Users\25868\Desktop\UE5\MapForgeTest\skill_patch_pv.txt"
$backupPath = "c:\Users\25868\.trae-cn\skills\ue5_json\SKILL.md.bak3"
# "派生要点" = 0x6D3E 0x751F 0x8981 0x70B9
$cjk = [char]0x6D3E + [char]0x751F + [char]0x8981 + [char]0x70B9
$oldHeading = "### 8.4 " + $cjk
$utf8 = [System.Text.Encoding]::UTF8
$skillContent = [System.IO.File]::ReadAllText($skillPath, $utf8)
$patchContent = [System.IO.File]::ReadAllText($patchPath, $utf8)
$idx = $skillContent.IndexOf($oldHeading)
Write-Output ("OLD_LENGTH=" + $skillContent.Length)
if ($idx -ge 0) {
    [System.IO.File]::WriteAllText($backupPath, $skillContent, $utf8)
    $newContent = $skillContent.Substring(0, $idx) + $patchContent + $skillContent.Substring($idx + $oldHeading.Length)
    [System.IO.File]::WriteAllText($skillPath, $newContent, $utf8)
    Write-Output ("REPLACE_OK at index " + $idx)
    Write-Output ("NEW_LENGTH=" + $newContent.Length)
} else {
    Write-Output "OLD_HEADING_NOT_FOUND"
}
