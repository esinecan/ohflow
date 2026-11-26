$ErrorActionPreference = 'Stop'
$worker = Split-Path -Parent $PSScriptRoot
$wrangler = Join-Path $worker 'node_modules\wrangler\bin\wrangler.js'
$config = Join-Path $worker 'wrangler.jsonc'
$local = Join-Path $worker 'pi-cloud.settings.local.json'
$name = 'pi-cloud'
if (Test-Path $local) {
    $settings = Get-Content $local -Raw | ConvertFrom-Json
    if ($settings.account_id) { $env:CLOUDFLARE_ACCOUNT_ID = $settings.account_id }
    if ($settings.name) { $name = $settings.name }
}

$token = [Environment]::GetEnvironmentVariable('PI_CLOUD_TOKEN', 'User')
if (-not $token) {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $token = -join ($bytes | ForEach-Object { $_.ToString('x2') })
    [Environment]::SetEnvironmentVariable('PI_CLOUD_TOKEN', $token, 'User')
}

$secrets = [ordered]@{ OHFLOW_TOKEN = $token }
$zai = [Environment]::GetEnvironmentVariable('ZAI_API_KEY', 'User')
if (-not $zai) { throw "ZAI_API_KEY is not set in your User environment" }
$secrets['ZAI_API_KEY'] = $zai
$deepseek = [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY', 'User')
if ($deepseek) { $secrets['DEEPSEEK_API_KEY'] = $deepseek }
$github = [Environment]::GetEnvironmentVariable('PI_CLOUD_GITHUB_TOKEN', 'User')
if ($github) { $secrets['GITHUB_TOKEN'] = $github }
$brave = [Environment]::GetEnvironmentVariable('BRAVE_API_KEY', 'User')
if ($brave) { $secrets['BRAVE_API_KEY'] = $brave }

$secrets | ConvertTo-Json -Compress | & node $wrangler secret bulk -c $config --name $name
if ($LASTEXITCODE -ne 0) { throw "wrangler secret bulk failed with exit code $LASTEXITCODE" }
"Set $($secrets.Keys -join ', ') on $name. ohflow reads the token from PI_CLOUD_TOKEN."
