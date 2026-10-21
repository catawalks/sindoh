param([string]$cmd, [int]$timeout = 30, [string]$port = 'COM3')
# Run one shell command on the printer's serial console and print the output.
# Fallback when no serial terminal/MCP tool is available:
#   powershell -File tools\serial_cmd.ps1 'uptime' 10
$p = New-Object System.IO.Ports.SerialPort $port,115200
$p.Open()
try {
    $p.ReadExisting() | Out-Null
    $p.Write("$cmd; echo RDY__`n")
    $buf = ''
    $deadline = (Get-Date).AddSeconds($timeout)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 200
        $buf += $p.ReadExisting()
        if ($buf -match "(?m)^RDY__\r?$") { break }
    }
    $buf
} finally { $p.Close() }
