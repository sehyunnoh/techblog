# Measure memory of a desktop app's whole process tree, the way Task Manager groups it.
# Usage: powershell -File measure.ps1 -Exe <path> -Args "<args>" -Name <label> -Runs 5 -SettleSec 20
param(
  [Parameter(Mandatory)][string]$Exe,
  [string]$AppArgs = "",
  [Parameter(Mandatory)][string]$Name,
  [int]$Runs = 5,
  [int]$SettleSec = 20,
  [string]$WorkDir = (Get-Location).Path
)

function Get-Tree([int]$rootPid) {
  $all = Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId
  $ids = New-Object System.Collections.Generic.HashSet[int]
  [void]$ids.Add($rootPid)
  do {
    $before = $ids.Count
    foreach ($p in $all) { if ($ids.Contains([int]$p.ParentProcessId)) { [void]$ids.Add([int]$p.ProcessId) } }
  } while ($ids.Count -ne $before)
  return $ids
}

$rows = @()
for ($i = 1; $i -le $Runs; $i++) {
  $proc = if ($AppArgs) { Start-Process -FilePath $Exe -ArgumentList $AppArgs -WorkingDirectory $WorkDir -PassThru }
          else { Start-Process -FilePath $Exe -WorkingDirectory $WorkDir -PassThru }
  Start-Sleep -Seconds $SettleSec
  $ids = Get-Tree $proc.Id
  $perf = Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | Where-Object { $ids.Contains([int]$_.IDProcess) }
  $pws = ($perf | Measure-Object WorkingSetPrivate -Sum).Sum / 1MB
  $ws  = ($perf | Measure-Object WorkingSet -Sum).Sum / 1MB
  $priv = ($perf | Measure-Object PrivateBytes -Sum).Sum / 1MB
  $rows += [pscustomobject]@{
    app = $Name; run = $i; processes = @($perf).Count
    private_ws_mb = [math]::Round($pws, 1)
    working_set_mb = [math]::Round($ws, 1)
    private_bytes_mb = [math]::Round($priv, 1)
  }
  Get-Tree $proc.Id | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Seconds 3
}
$rows | Format-Table -AutoSize | Out-String | Write-Host
$med = $rows | Sort-Object private_ws_mb | Select-Object -Index ([int][math]::Floor($Runs / 2))
Write-Host ("{0}: median private working set = {1} MB ({2} processes)" -f $Name, $med.private_ws_mb, $med.processes)
$rows | ConvertTo-Csv -NoTypeInformation
