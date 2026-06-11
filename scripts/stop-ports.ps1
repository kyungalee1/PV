param(
    [int[]]$Ports = @(8000, 5173)
)

foreach ($port in $Ports) {
    $pids = @()
    $pids += Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    $netstat = netstat -ano | Select-String ":$port\s+.*LISTENING"
    foreach ($line in $netstat) {
        if ($line -match '\s+(\d+)\s*$') {
            $pids += [int]$Matches[1]
        }
    }
    foreach ($procId in ($pids | Where-Object { $_ -gt 0 } | Select-Object -Unique)) {
        Write-Host "Stopping PID $procId on port $port"
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
}

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -match 'python(\.exe)?' -and
        (
            $_.CommandLine -match 'uvicorn\s+app\.main:app' -or
            $_.CommandLine -match 'multiprocessing-fork' -or
            $_.CommandLine -match 'spawn_main'
        )
    } |
    ForEach-Object {
        Write-Host "Stopping python PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Start-Sleep -Seconds 1
