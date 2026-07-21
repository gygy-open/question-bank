#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Install Question Bank as a Windows service and open the LAN firewall port.

.DESCRIPTION
    Registers the bundled WinSW wrapper as an auto-start Windows service (runs in
    the background with no console window, restarts on crash, survives logout),
    then opens the inbound firewall port so other terminals on the network can
    reach the server by IP. Finally prints the URLs to share with clients.

    Run this from the extracted release folder, in an ELEVATED PowerShell
    (right-click > Run as administrator).

.PARAMETER Port
    TCP port to open in the firewall. Must match the PORT value in
    question-bank-service.xml (default 8000).

.EXAMPLE
    .\install-service.ps1
    .\install-service.ps1 -Port 9000
#>
[CmdletBinding()]
param(
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$wrapper = Join-Path $here 'question-bank-service.exe'

if (-not (Test-Path $wrapper)) {
    throw "找不到 $wrapper。请在解压后的完整发布目录中运行本脚本。"
}

Write-Host '注册并启动 Question Bank 服务...' -ForegroundColor Cyan
& $wrapper install
& $wrapper start

# Open the firewall so other terminals can reach the server over the LAN.
$ruleName = "Question Bank ($Port)"
if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort $Port -Profile Any | Out-Null
    Write-Host "已放行防火墙入站端口 $Port" -ForegroundColor Green
} else {
    Write-Host "防火墙规则已存在,跳过: $ruleName" -ForegroundColor DarkGray
}

# Show the machine's LAN IPv4 addresses so clients know where to connect.
$ips = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notmatch '^127\.' -and $_.PrefixOrigin -ne 'WellKnown' } |
    Select-Object -ExpandProperty IPAddress

Write-Host ''
Write-Host '安装完成,服务已在后台运行(开机自启)。' -ForegroundColor Green
Write-Host '首次使用请在本机打开下面的地址完成安装向导(选数据库 + 建管理员):'
Write-Host "  http://localhost:$Port" -ForegroundColor Yellow
Write-Host ''
Write-Host '其他终端可通过以下地址访问:' -ForegroundColor Green
foreach ($ip in $ips) { Write-Host "  http://${ip}:$Port" -ForegroundColor Yellow }
