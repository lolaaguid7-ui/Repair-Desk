$ErrorActionPreference = 'Stop'
$repairUrl = 'http://127.0.0.1:5001/'
function Test-RepairDesk {
    try {
        $response = Invoke-WebRequest -Uri $repairUrl -UseBasicParsing -TimeoutSec 2
        return $response.Content -match '<title>[^<]*Repair Desk[^<]*</title>'
    } catch { return $false }
}
try {
    if (-not (Test-RepairDesk)) {
        $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $python)) {
            $python = Join-Path (Split-Path $PSScriptRoot -Parent) '.venv\Scripts\python.exe'
        }
        if (-not (Test-Path -LiteralPath $python)) { throw 'Python environment not found. Please restore the project environment.' }
        $runFile = Join-Path $PSScriptRoot 'run.py'
        $null = Start-Process -FilePath $python -ArgumentList ('"' + $runFile + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
        $ready = $false
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            Start-Sleep -Milliseconds 500
            if (Test-RepairDesk) { $ready = $true; break }
        }
        if (-not $ready) { throw 'Repair Desk could not start on port 5001. Open Start Repair Desk.cmd in the project folder to see the error.' }
    }
    Start-Process $repairUrl
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Repair Desk') | Out-Null
}
