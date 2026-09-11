Add-Type -AssemblyName System.Windows.Forms
$files = Get-ChildItem "c:\Users\25868\Desktop\UE5\screenshots\shot_*.png" | Sort-Object Name | Select-Object -ExpandProperty FullName
[System.Windows.Forms.Clipboard]::SetFileDropList($files)
Write-Host "Clipboard set with $($files.Count) files"
$files | ForEach-Object { Write-Host $_ }
