# 创建 Windows 快捷方式
param(
    [Parameter(Mandatory=$true)][string]$TargetPath,
    [Parameter(Mandatory=$true)][string]$WorkingDir,
    [Parameter(Mandatory=$true)][string]$ShortcutPath,
    [string]$IconPath = "",
    [string]$Description = "tsumugi 音频转 MIDI 助手"
)

try {
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($ShortcutPath)
    $sc.TargetPath = $TargetPath
    $sc.WorkingDirectory = $WorkingDir
    $sc.Description = $Description
    $sc.WindowStyle = 7
    if ($IconPath -ne "" -and (Test-Path $IconPath)) {
        $sc.IconLocation = $IconPath
    }
    $sc.Save()
    Write-Output "SHORTCUT_OK"
} catch {
    Write-Output "SHORTCUT_FAIL: $_"
    exit 1
}