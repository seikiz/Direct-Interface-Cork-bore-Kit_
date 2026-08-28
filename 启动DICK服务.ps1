$dist = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = "python"
foreach ($s in @("net.py", "trpg_server.py")) {
  $run = $false
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.CommandLine -match [regex]::Escape($s)) { $run = $true }
  }
  if (-not $run) { Start-Process -FilePath $py -ArgumentList @($s) -WorkingDirectory $dist -WindowStyle Hidden }
}
