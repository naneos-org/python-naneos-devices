<#
.SYNOPSIS
Install the naneos tray app on Windows.

.DESCRIPTION
Installs uv if you do not have it, installs the naneos-devices package with the tray app
into its own environment, adds a Start Menu shortcut and starts the app at every login.
Run it again to update: it stops the running app, installs the new version and starts it
again. Changes only your user account, needs no administrator rights.

This is the desktop app. The Raspberry Pi uploader has its own installer (install.sh).

.EXAMPLE
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install-desktop.ps1 | iex"

.EXAMPLE
# With options: `irm | iex` cannot pass arguments, so turn the script into a script block.
powershell -ExecutionPolicy ByPass -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install-desktop.ps1))) -Version 2.1.0 -NoStart"

.EXAMPLE
# Install a branch from GitHub, to test it before it is released. -Ref is a normal parameter,
# so this is one line and needs no environment variable. (The plain `irm | iex` form takes no
# arguments; it reads NANEOS_REF, NANEOS_VERSION and NANEOS_PYTHON from the environment.)
powershell -ExecutionPolicy ByPass -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/naneos-org/python-naneos-devices/branch-name/installers/install-desktop.ps1))) -Ref branch-name"

.EXAMPLE
# Uninstall (uv and the log files stay)
powershell -ExecutionPolicy ByPass -c "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install-desktop.ps1))) -Uninstall"

.PARAMETER Version
Install this release instead of the latest one. Also read from $env:NANEOS_VERSION.

.PARAMETER Pre
Also consider pre-releases (release candidates).

.PARAMETER Ref
Install straight from GitHub (a branch or tag, for testing). Also read from $env:NANEOS_REF.

.PARAMETER Python
Python for the app. Default 3.13; uv downloads it if needed. Also read from $env:NANEOS_PYTHON.

.PARAMETER NoAutostart
Do not start the app at login.

.PARAMETER NoStart
Do not start the app now.

.PARAMETER Uninstall
Stop the app and remove it.

For developers: $env:NANEOS_REQUIREMENT = "naneos-devices[gui] @ file:///C:/path/to/checkout"
installs that instead of a release.
#>
param(
    [string]$Version = $env:NANEOS_VERSION,
    [switch]$Pre,
    [string]$Ref = $env:NANEOS_REF,
    [string]$Python = $env:NANEOS_PYTHON,
    [switch]$NoAutostart,
    [switch]$NoStart,
    [switch]$Uninstall
)

# Everything is in a function: a plain `exit` in a script run with `irm | iex` would close
# the window of the user. Errors are thrown instead.
function Install-NaneosDesktop {
    param(
        [string]$Version,
        [bool]$Pre,
        [string]$Ref,
        [string]$Python,
        [bool]$NoAutostart,
        [bool]$NoStart,
        [bool]$Uninstall
    )

    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'

    $repo = 'naneos-org/python-naneos-devices'
    $package = 'naneos-devices'
    if (-not $Python) { $Python = '3.13' }
    if ($Version -and $Ref) { throw 'Use either -Version or -Ref, not both.' }

    $logDir = Join-Path $env:LOCALAPPDATA 'naneos\naneos-devices\Logs'
    $shortcut = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Naneos Devices.lnk'

    # Run a program, show its output, return its exit code. Native programs write progress to
    # stderr, which the default error handling would turn into an error, so relax it here.
    function Invoke-Native {
        param([string]$File, [string[]]$Arguments)
        $old = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            & $File @Arguments | Out-Host
            return $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $old
        }
    }

    # Like Invoke-Native, but returns the output (stdout only) as one string.
    function Get-NativeOutput {
        param([string]$File, [string[]]$Arguments)
        $old = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $text = & $File @Arguments 2>$null
            return ($text -join "`n")
        }
        finally {
            $ErrorActionPreference = $old
        }
    }

    # Like Get-NativeOutput, but returns only the exit code and keeps quiet.
    function Get-NativeExitCode {
        param([string]$File, [string[]]$Arguments)
        $old = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            & $File @Arguments 2>$null | Out-Null
            return $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $old
        }
    }

    function Find-Uv {
        $found = Get-Command uv -ErrorAction SilentlyContinue
        if ($found) { return $found.Source }
        # A fresh uv is not on the PATH of this window yet: look where its installer puts it.
        $dirs = @(
            $env:UV_INSTALL_DIR,
            $env:XDG_BIN_HOME,
            (Join-Path $env:USERPROFILE '.local\bin'),
            (Join-Path $env:USERPROFILE '.cargo\bin')
        ) | Where-Object { $_ }
        foreach ($dir in $dirs) {
            $candidate = Join-Path $dir 'uv.exe'
            if (Test-Path $candidate) { return $candidate }
        }
        return $null
    }

    # Ask the running tray app to quit and wait for it. The console python of the tool
    # environment is used, because PowerShell does not wait for the windowless naneos-gui.exe.
    function Stop-NaneosApp {
        param([string]$ToolRoot)
        $toolPython = Join-Path $ToolRoot 'Scripts\python.exe'
        if (Test-Path $toolPython) {
            [void](Invoke-Native $toolPython @('-m', 'naneos.gui', '--quit', '--timeout', '30'))
        }
        # An app that did not answer, or one too old to know --quit. Windows will not replace
        # the files of a running program, so nothing of the environment may stay alive.
        $root = $ToolRoot.TrimEnd('\') + '\'
        Get-Process -ErrorAction SilentlyContinue | ForEach-Object {
            $path = $null
            try { $path = $_.Path } catch { $path = $null }  # no access to a system process
            if ($path -and $path.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
                Write-Host "Stopping $($_.ProcessName) ($($_.Id)) ..."
                Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            }
        }
        Start-Sleep -Milliseconds 500
    }

    function Remove-Shortcut {
        if (Test-Path $shortcut) { Remove-Item $shortcut -Force }
    }

    $uv = Find-Uv

    if ($Uninstall) {
        Write-Host 'Removing the naneos tray app ...'
        if ($uv) {
            $toolRoot = Join-Path ((Get-NativeOutput $uv @('tool', 'dir')).Trim()) $package
            Stop-NaneosApp $toolRoot
            $toolPython = Join-Path $toolRoot 'Scripts\python.exe'
            if (Test-Path $toolPython) {
                [void](Invoke-Native $toolPython @('-m', 'naneos.gui', '--autostart', 'off'))
            }
            [void](Invoke-Native $uv @('tool', 'uninstall', $package))
        }
        Remove-Shortcut
        Write-Host "Removed. uv, the log files in $logDir and your data stay."
        return
    }

    if (-not $uv) {
        Write-Host 'Installing uv ...'
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        $uv = Find-Uv
        if (-not $uv) { throw 'uv was installed but I cannot find it. Open a new window and run this again.' }
    }
    Write-Host "Using $uv"

    $toolRoot = Join-Path ((Get-NativeOutput $uv @('tool', 'dir')).Trim()) $package
    $toolPython = Join-Path $toolRoot 'Scripts\python.exe'

    # Was start at login switched off by the user? An update must not turn it back on.
    $keepAutostartOff = $false
    if (Test-Path $toolPython) {
        $status = Get-NativeOutput $toolPython @('-m', 'naneos.gui', '--autostart', 'status')
        if ($status -match ': off') { $keepAutostartOff = $true }
    }

    Stop-NaneosApp $toolRoot

    if ($env:NANEOS_REQUIREMENT) {
        $requirement = $env:NANEOS_REQUIREMENT
    }
    elseif ($Version) {
        $requirement = "$package[gui]==$Version"
    }
    elseif ($Ref) {
        $requirement = "$package[gui] @ https://github.com/$repo/archive/$Ref.tar.gz"
    }
    else {
        $requirement = "$package[gui]"
    }

    Write-Host "Installing $requirement (Python $Python) ..."
    $installArgs = @('tool', 'install', '--force', '--python', $Python)
    if ($Pre) { $installArgs += @('--prerelease', 'allow') }
    $installArgs += $requirement
    $code = Invoke-Native $uv $installArgs
    if ($code -ne 0) { throw "uv could not install $requirement (exit code $code)." }
    if (-not (Test-Path $toolPython)) { throw "The installation finished but $toolPython does not exist." }

    # An old release installs without an error: uv only warns that it has no extra "gui". The tray
    # app first ships in 2.1.0, so say what is wrong instead of failing later on an empty value.
    if ((Get-NativeExitCode $toolPython @('-c', 'import naneos.gui.app')) -ne 0) {
        $installedVersion = (Get-NativeOutput $toolPython @('-c', 'import importlib.metadata as m; print(m.version(''naneos-devices''))')).Trim()
        throw ("The installed $package $installedVersion does not contain the tray app (it first ships in 2.1.0). " +
            'Either that release is not published yet, or -Version is too old. To install a branch from GitHub ' +
            'instead, run the script with -Ref branch-name, see the second example at the top of the script: ' +
            '& ([scriptblock]::Create((irm <script url>))) -Ref branch-name')
    }

    # The path of the launcher and the icon come from the installed package.
    $guiExe = (Get-NativeOutput $toolPython @('-c', 'from naneos.gui.integration import entry_point; print(entry_point())')).Trim()
    # (No double quotes in these arguments: Windows PowerShell 5.1 strips them.)
    $icon = (Get-NativeOutput $toolPython @('-c', 'from naneos.gui.integration import icon_file; print(icon_file(''ico''))')).Trim()
    if (-not $guiExe -or -not (Test-Path $guiExe)) { throw "The installation finished but the app '$guiExe' does not exist." }

    # Start Menu entry, so the app can be started again after Quit.
    $wsh = New-Object -ComObject WScript.Shell
    $link = $wsh.CreateShortcut($shortcut)
    $link.TargetPath = $guiExe
    $link.Description = 'Shows and uploads the data of your naneos Partector devices'
    if ($icon -and (Test-Path $icon)) { $link.IconLocation = $icon }
    $link.Save()

    if (-not $NoAutostart -and -not $keepAutostartOff) {
        [void](Invoke-Native $toolPython @('-m', 'naneos.gui', '--autostart', 'on'))
    }

    if (-not $NoStart) {
        Start-Process -FilePath $guiExe
    }

    $installed = (Get-NativeOutput $toolPython @('-m', 'naneos.gui', '--version')).Trim()
    $url = "https://raw.githubusercontent.com/$repo/master/installers/install-desktop.ps1"
    Write-Host ''
    Write-Host "$installed is installed."
    Write-Host "  Log files:  $logDir"
    Write-Host '  Update:     run the same command again'
    Write-Host "  Uninstall:  powershell -ExecutionPolicy ByPass -c ""& ([scriptblock]::Create((irm $url))) -Uninstall"""
}

Install-NaneosDesktop -Version $Version -Pre $Pre.IsPresent -Ref $Ref -Python $Python `
    -NoAutostart $NoAutostart.IsPresent -NoStart $NoStart.IsPresent -Uninstall $Uninstall.IsPresent
