# Create a desktop shortcut for the Xianyu monitor.
#
# The shortcut targets the project venv's pythonw.exe + open_monitor.py, so the
# service starts without a console window and the browser opens as soon as the
# port answers.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\make_desktop_shortcut.ps1
#
# NOTE: keep this file pure ASCII. powershell.exe reads scripts using the ANSI
# code page, so the Chinese shortcut name is built from code points instead of
# being typed literally (a literal one gets mangled and the file is never
# created).

$ErrorActionPreference = "Stop"

$root    = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath("Desktop")

# name: Xianyu Zhineng Jiankong  ->  "xian yu zhi neng jian kong"
$chars   = @(0x95F2, 0x9C7C, 0x667A, 0x80FD, 0x76D1, 0x63A7)
$name    = -join ($chars | ForEach-Object { [char]$_ })
$lnkPath = Join-Path $desktop ($name + ".lnk")

$pyw  = Join-Path $root ".venv\Scripts\pythonw.exe"
$py   = Join-Path $root ".venv\Scripts\python.exe"
$main = Join-Path $root "open_monitor.py"
$icon = Join-Path $root "static\brand\logo.ico"

if (-not (Test-Path -LiteralPath $main)) { throw "missing entry script: $main" }

$exe = if (Test-Path -LiteralPath $pyw) { $pyw }
       elseif (Test-Path -LiteralPath $py) { $py }
       else { throw "missing python in .venv\Scripts" }

$sh = New-Object -ComObject WScript.Shell
$sc = $sh.CreateShortcut($lnkPath)
$sc.TargetPath       = $exe
$sc.Arguments        = '"' + $main + '"'
$sc.WorkingDirectory = $root
$sc.Description      = "Xianyu AI Monitor - start the service and open the web UI"
$sc.WindowStyle      = 7   # minimized; pythonw has no console anyway

if (Test-Path -LiteralPath $icon) {
    $sc.IconLocation = "$icon,0"
} else {
    $sc.IconLocation = "$env:SystemRoot\System32\shell32.dll,13"
}

$sc.Save()

if (-not (Test-Path -LiteralPath $lnkPath)) { throw "shortcut not created: $lnkPath" }

Write-Output ("OK  ->  " + $lnkPath)
Write-Output ("target: " + $exe)
