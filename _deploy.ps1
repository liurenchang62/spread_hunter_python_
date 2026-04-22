# Deploy script for Vultr server
$serverIP = "45.63.61.93"
$username = "root"
$password = "Vt7]z*2?a!eK!PTY"

# Create temporary expect script for auto SSH login
$expectScript = @'
spawn ssh root@45.63.61.93
expect "password:"
send "Vt7]z*2?a!eK!PTY\r"
expect "$"
send "echo 'SSH Connected Successfully'\r"
expect "$"
send "exit\r"
interact
'@

Write-Host "Testing SSH connection to $serverIP..."

# Try to connect and check server status
try {
    $env:SSH_ASKPASS = ""
    $proc = Start-Process -FilePath "ssh" -ArgumentList "-o StrictHostKeyChecking=no -o PasswordAuthentication=yes -o ConnectTimeout=10 ${username}@${serverIP} echo 'Server is up'" -Wait -PassThru -WindowStyle Hidden
    Write-Host "SSH process completed with code: $($proc.ExitCode)"
} catch {
    Write-Host "Error: $_"
}
