# Requires Python 3.9+. All arguments are passed to the shared cross-platform CLI.
# Example: .\setup-external-api.ps1 --base-url https://api.example.com --model model-id
$ErrorActionPreference = 'Stop'
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 "$PSScriptRoot/setup_external_api.py" @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python "$PSScriptRoot/setup_external_api.py" @args
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    & python3 "$PSScriptRoot/setup_external_api.py" @args
} else {
    Write-Error 'Python 3.9 or newer is required. Install Python, then rerun this script.'
    exit 1
}
exit $LASTEXITCODE
