param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path $VenvPython) {
        $Python = $VenvPython
    }
    else {
        $Python = "python"
    }
}

function Invoke-PyneCheck {
    param(
        [string[]]$Arguments
    )

    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $Python $($Arguments -join ' ')"
    }
}

Push-Location $Root
try {
    Invoke-PyneCheck -Arguments @("-m", "ruff", "check", ".")
    Invoke-PyneCheck -Arguments @("-m", "pytest")
    Invoke-PyneCheck -Arguments @("scripts/strategy_capture_scaffold.py", "--check")
    Invoke-PyneCheck -Arguments @(
        "scripts/strategy_capture_diff.py",
        "--assertion",
        "parity"
    )
    Invoke-PyneCheck -Arguments @(
        "scripts/ta_capture_diff.py",
        "--assertion",
        "parity"
    )
    $Dist = Join-Path $env:TEMP "pyne-runtime-dist-check"
    if (Test-Path $Dist) {
        Remove-Item -LiteralPath $Dist -Recurse -Force
    }
    Invoke-PyneCheck -Arguments @("-m", "build", "--outdir", $Dist)
    $Artifacts = Get-ChildItem -LiteralPath $Dist | ForEach-Object { $_.FullName }
    $TwineArgs = @("-m", "twine", "check") + $Artifacts
    Invoke-PyneCheck -Arguments $TwineArgs
}
finally {
    Pop-Location
}
