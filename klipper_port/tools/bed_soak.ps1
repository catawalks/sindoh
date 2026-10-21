param([double]$target, [int]$soakMin = 10, [int]$maxMin = 9, [string]$hostname = '10.10.0.21')
# Watch the bed heat to $target, then time a soak. Keeps state in
# $env:TEMP\bed_soak_<target>.txt so it can be called repeatedly
# (each call returns after at most $maxMin minutes).
$q = "http://${hostname}:7125/printer/objects/query?heater_bed"
$state = "$env:TEMP\bed_soak_$target.txt"
$reached = if (Test-Path $state) { [datetime](Get-Content $state) } else { $null }
$end = (Get-Date).AddMinutes($maxMin)
$powers = @()
while ((Get-Date) -lt $end) {
    $b = (Invoke-RestMethod $q).result.status.heater_bed
    if ($b.target -ne $target) {
        "{0:HH:mm:ss} ABORT: target is now {1} (idle timeout or shutdown?), klipper {2:N2}" -f (Get-Date), $b.target, $b.temperature
        if (Test-Path $state) { Remove-Item $state }
        return
    }
    if (-not $reached -and $b.temperature -ge $target - 0.3) {
        $reached = Get-Date; Set-Content $state $reached.ToString('o')
        "{0:HH:mm:ss} reached {1:N2}" -f $reached, $b.temperature
    }
    if ($reached) {
        $powers += $b.power
        $soaked = ((Get-Date) - $reached).TotalMinutes
        if ($soaked -ge $soakMin) {
            $avg = ($powers | Select-Object -Last 12 | Measure-Object -Average).Average
            "{0:HH:mm:ss} SOAK DONE ({1:N1} min): klipper {2:N2} target {3} avg power {4:N2}" -f (Get-Date), $soaked, $b.temperature, $b.target, $avg
            Remove-Item $state
            return
        }
    }
    Start-Sleep 10
}
$b = (Invoke-RestMethod $q).result.status.heater_bed
$msg = if ($reached) { "soaking {0:N1} of $soakMin min" -f ((Get-Date) - $reached).TotalMinutes } else { "still heating" }
"{0:HH:mm:ss} {1}: klipper {2:N2} power {3:N2}" -f (Get-Date), $msg, $b.temperature, $b.power
