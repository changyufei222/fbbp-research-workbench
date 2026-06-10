. (Join-Path $PSScriptRoot 'common.ps1')

Write-Step 'Starting FBBP HTTP MCP server inside WSL from project-local sources'

Stop-ProcessesByPort -Ports @(8000)

$scriptPath = Join-Path $PSScriptRoot 'start_fbbp_http_mcp_wsl.sh'
$scriptBody = Get-Content $scriptPath -Raw
$workspaceRootB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Convert-ToWslPath (Get-WorkspaceRoot))))
$repoRootB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Convert-ToWslPath (Get-RepoRoot))))
$wslRuntimeRoot = '/tmp/fbbp_http_mcp_runtime'
$scriptBody | wsl bash -lc "export FBBP_WORKSPACE_ROOT_B64='$workspaceRootB64'; export FBBP_REPO_ROOT_B64='$repoRootB64'; export FBBP_WSL_RUNTIME_ROOT='$wslRuntimeRoot'; bash -s"

$wslIp = Get-WslPrimaryIp
$mcpUrl = $null

function Test-McpEndpoint {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -Method Get -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            if ($resp.StatusCode -ge 200) {
                return $true
            }
        } catch {
            $statusCode = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { -1 }
            if ($statusCode -in @(405, 406)) {
                return $true
            }
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

if (Test-McpEndpoint -Url 'http://127.0.0.1:8000/mcp' -TimeoutSeconds 30) {
    $mcpUrl = 'http://127.0.0.1:8000/mcp'
} elseif (Test-McpEndpoint -Url "http://${wslIp}:8000/mcp" -TimeoutSeconds 15) {
    $mcpUrl = "http://${wslIp}:8000/mcp"
} else {
    Write-Warning "MCP HTTP probe did not succeed from Windows within the expected window; using current WSL IP $wslIp based on confirmed WSL listener."
    $mcpUrl = "http://${wslIp}:8000/mcp"
}

foreach ($jsonPath in @(
    (Get-DeerflowExtensionsPath),
    (Join-Path (Get-WorkspaceRoot) 'configs/extensions_config.fbbp.example.json'),
    (Join-Path (Get-WorkspaceRoot) 'configs/extensions_config.fbtp.example.json')
)) {
    if (-not (Test-Path $jsonPath)) {
        continue
    }
    $obj = Get-Content $jsonPath -Raw | ConvertFrom-Json
    foreach ($serverName in @('fbbp-rag', 'fbtp-rag')) {
        if ($obj.mcpServers.PSObject.Properties.Name -notcontains $serverName) {
            continue
        }
        $obj.mcpServers.$serverName.type = 'http'
        $obj.mcpServers.$serverName.url = $mcpUrl
        $obj.mcpServers.$serverName.description = 'Private FBBP knowledge retrieval over ragkb (HTTP MCP)'
        $obj.mcpServers.$serverName.PSObject.Properties.Remove('command')
        $obj.mcpServers.$serverName.PSObject.Properties.Remove('args')
        $obj.mcpServers.$serverName.PSObject.Properties.Remove('env')
    }
    $jsonText = $obj | ConvertTo-Json -Depth 20
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($jsonPath, $jsonText, $utf8NoBom)
}

Write-Host "FBBP HTTP MCP server is ready at $mcpUrl"
