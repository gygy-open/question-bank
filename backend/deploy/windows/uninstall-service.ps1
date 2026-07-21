#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Stop and remove the Question Bank Windows service and its firewall rule.

.DESCRIPTION
    Reverses install-service.ps1: stops the service, unregisters it, and removes
    the inbound firewall rule. Application data (database, config.json, uploads)
    lives under the per-user data directory and is NOT touched.

    Run from the extracted release folder in an ELEVATED PowerShell.

.PARAMETER Port
    The firewall port that was opened during install (default 8000).
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

Write-Host '停止并卸载 Question Bank 服务...' -ForegroundColor Cyan
& $wrapper stop
& $wrapper uninstall

$ruleName = "Question Bank ($Port)"
Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

Write-Host '已停止并卸载服务,移除防火墙规则。应用数据未删除。' -ForegroundColor Green
