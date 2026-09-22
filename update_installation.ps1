param(
    [ValidateSet('Prepare', 'Apply', 'Rollback')][string]$Mode = 'Prepare',
    [Parameter(Mandatory = $true)][string]$InstallPath,
    [string]$BundlePath = (Join-Path $PSScriptRoot 'SunriseCast'),
    [string]$BackupRoot = (Join-Path $env:LOCALAPPDATA 'SunriseCast\backups'),
    [string]$BackupPath
)
$ErrorActionPreference = 'Stop'

function Assert-InRoot([string]$Path, [string]$Root) {
    $Absolute = [IO.Path]::GetFullPath($Path)
    $Boundary = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    if (-not $Absolute.StartsWith($Boundary, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Caminho fora do diretório esperado: $Absolute"
    }
}

function File-Sha256([string]$Path) {
    $Hasher = [Security.Cryptography.SHA256]::Create()
    $Stream = [IO.FileStream]::new($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try { return [BitConverter]::ToString($Hasher.ComputeHash($Stream)).Replace('-', '') }
    finally { $Stream.Dispose(); $Hasher.Dispose() }
}

function File-Inventory([string]$Root) {
    $Prefix = $Root.TrimEnd('\') + '\'
    @(Get-ChildItem -LiteralPath $Root -File -Recurse -Force | ForEach-Object {
        [PSCustomObject]@{ path = $_.FullName.Substring($Prefix.Length); sha256 = (File-Sha256 $_.FullName) }
    })
}

function Verify-Inventory([string]$Root, $Inventory) {
    foreach ($Entry in $Inventory) {
        $File = Join-Path $Root $Entry.path
        Assert-InRoot $File $Root
        if (-not (Test-Path -LiteralPath $File -PathType Leaf) -or (File-Sha256 $File) -ne $Entry.sha256) {
            throw "Verificação de integridade falhou: $File"
        }
    }
}

function Get-RunningInstallationProcess([string]$Root) {
    $Boundary = $Root.TrimEnd('\') + '\'
    @(Get-CimInstance Win32_Process -Filter "Name = 'SunriseCast.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.ExecutablePath -and $_.ExecutablePath.StartsWith($Boundary, [StringComparison]::OrdinalIgnoreCase)
    })
}

function Copy-FileShared([string]$Source, [string]$Destination) {
    $DestinationFolder = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $DestinationFolder -Force | Out-Null
    $InputStream = [IO.FileStream]::new($Source, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        $OutputStream = [IO.FileStream]::new($Destination, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $InputStream.CopyTo($OutputStream) }
        finally { $OutputStream.Dispose() }
    } finally {
        $InputStream.Dispose()
    }
}

function Copy-DirectoryShared([string]$SourceRoot, [string]$DestinationRoot) {
    New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
    $Prefix = $SourceRoot.TrimEnd('\') + '\'
    Get-ChildItem -LiteralPath $SourceRoot -Directory -Recurse -Force | ForEach-Object {
        $Relative = $_.FullName.Substring($Prefix.Length)
        New-Item -ItemType Directory -Path (Join-Path $DestinationRoot $Relative) -Force | Out-Null
    }
    Get-ChildItem -LiteralPath $SourceRoot -File -Recurse -Force | ForEach-Object {
        $Relative = $_.FullName.Substring($Prefix.Length)
        Copy-FileShared $_.FullName (Join-Path $DestinationRoot $Relative)
    }
}

function Move-Path([string]$Source, [string]$Destination) {
    if (Test-Path -LiteralPath $Destination) {
        throw "Destino ja existe: $Destination"
    }
    if (Test-Path -LiteralPath $Source -PathType Container) {
        [IO.Directory]::Move($Source, $Destination)
    } else {
        [IO.File]::Move($Source, $Destination)
    }
}

function New-Backup {
    $Folder = Join-Path $BackupRoot ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
    $Snapshot = Join-Path $Folder 'snapshot'
    New-Item -ItemType Directory -Path $Snapshot -Force | Out-Null
    Copy-DirectoryShared $InstallPath $Snapshot
    $Inventory = File-Inventory $Snapshot
    Verify-Inventory $Snapshot $Inventory
    $Manifest = [PSCustomObject]@{ installPath = $InstallPath; createdAt = (Get-Date).ToString('o'); files = $Inventory }
    $Manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Folder 'backup-manifest.json') -Encoding UTF8
    return $Folder
}

$InstallPath = (Resolve-Path -LiteralPath $InstallPath).Path.TrimEnd('\')
$BackupRoot = [IO.Path]::GetFullPath($BackupRoot)
if ($BackupRoot.StartsWith($InstallPath + '\', [StringComparison]::OrdinalIgnoreCase) -or $BackupRoot -eq $InstallPath) {
    throw 'O backup deve ficar fora da instalação.'
}
$Running = Get-RunningInstallationProcess $InstallPath
if ($Running.Count) { throw 'Feche o SunriseCast pela bandeja antes de continuar. Nenhum processo será encerrado à força.' }

if ($Mode -eq 'Rollback') {
    if (-not $BackupPath) { throw 'Informe -BackupPath com o backup desejado.' }
    $BackupPath = (Resolve-Path -LiteralPath $BackupPath).Path
    $Manifest = Get-Content -LiteralPath (Join-Path $BackupPath 'backup-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Manifest.installPath -ne $InstallPath) { throw 'O backup pertence a outra instalação.' }
    $Snapshot = Join-Path $BackupPath 'snapshot'
    Verify-Inventory $Snapshot $Manifest.files
    $BeforeRollback = New-Backup
    $Displaced = Join-Path $BeforeRollback 'displaced'
    New-Item -ItemType Directory -Path $Displaced | Out-Null
    Get-ChildItem -LiteralPath $InstallPath -Force | ForEach-Object {
        Assert-InRoot $_.FullName $InstallPath
        Move-Item -LiteralPath $_.FullName -Destination $Displaced
    }
    Get-ChildItem -LiteralPath $Snapshot -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $InstallPath -Recurse -Force
    }
    Verify-Inventory $InstallPath $Manifest.files
    Write-Host "Backup restaurado. Estado anterior à reversão preservado em: $BeforeRollback"
    return
}

$BundlePath = (Resolve-Path -LiteralPath $BundlePath).Path
if (-not (Test-Path -LiteralPath (Join-Path $InstallPath 'SunriseCast.exe'))) {
    throw 'A pasta informada não contém uma instalação existente do SunriseCast.'
}
foreach ($Name in @('SunriseCast.exe', '_internal')) {
    if (-not (Test-Path -LiteralPath (Join-Path $BundlePath $Name))) { throw "Pacote incompleto: $Name" }
}
$Personal = Get-ChildItem -LiteralPath $BundlePath -Recurse -Force | Where-Object {
    $_.Name -in @('.env', '.spotify_cache', 'podcasts.json', 'settings.json', 'state.json', 'app.log')
}
if ($Personal) { throw 'O pacote de distribuição contém dados pessoais.' }
$SavedBackup = New-Backup
Write-Host "Backup verificado: $SavedBackup"
if ($Mode -eq 'Prepare') {
    Write-Host 'Preparação concluída. A instalação ainda não foi alterada. Use -Mode Apply para atualizar.'
    return
}

$Stage = Join-Path $InstallPath ('.sunrisecast-update-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Stage | Out-Null
foreach ($Name in @('SunriseCast.exe', '_internal')) {
    Copy-Item -LiteralPath (Join-Path $BundlePath $Name) -Destination $Stage -Recurse
}
Verify-Inventory $Stage (File-Inventory $BundlePath)
$Previous = Join-Path $InstallPath ('.sunrisecast-previous-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Previous | Out-Null
try {
    foreach ($Name in @('SunriseCast.exe', '_internal')) {
        $Existing = Join-Path $InstallPath $Name
        Assert-InRoot $Existing $InstallPath
        if (Test-Path -LiteralPath $Existing) {
            Move-Path $Existing (Join-Path $Previous $Name)
        }
        $Staged = Join-Path $Stage $Name
        Assert-InRoot $Staged $InstallPath
        Move-Path $Staged (Join-Path $InstallPath $Name)
    }
    # Older builds did not persist 429 deadlines. Carry the latest unexpired log deadline
    # into a small sidecar consumed once by state migration; keep state.json byte-for-byte.
    $Log = Join-Path $InstallPath 'logs\app.log'
    $LegacyWaitFile = Join-Path $InstallPath 'data\legacy_spotify_wait.json'
    if ((Test-Path -LiteralPath $Log) -and -not (Test-Path -LiteralPath $LegacyWaitFile)) {
        $LastWait = Get-Content -LiteralPath $Log -Tail 20000 | Select-String '^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+.*Retry will occur after: (\d+) s' | Select-Object -Last 1
        if ($LastWait) {
            $Match = $LastWait.Matches[0]
            $Start = [DateTime]::ParseExact($Match.Groups[1].Value, 'yyyy-MM-dd HH:mm:ss', [Globalization.CultureInfo]::InvariantCulture)
            $Until = $Start.AddSeconds([double]$Match.Groups[2].Value)
            if ($Until -gt (Get-Date)) {
                $Wait = @{ until = $Until.ToUniversalTime().ToString('o'); reason = 'RATE_LIMITED'; retry_after = $Match.Groups[2].Value; seconds = [int]$Match.Groups[2].Value }
                $Wait | ConvertTo-Json | Set-Content -LiteralPath $LegacyWaitFile -Encoding UTF8
            }
        }
    }
    $OldManifest = Get-Content -LiteralPath (Join-Path $SavedBackup 'backup-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $PersonalInventory = @($OldManifest.files | Where-Object { $_.path -ne 'SunriseCast.exe' -and -not $_.path.StartsWith('_internal\') })
    Verify-Inventory $InstallPath $PersonalInventory
    $ArchivedPrevious = Join-Path $SavedBackup 'previous-binaries'
    try {
        Move-Path $Previous $ArchivedPrevious
    } catch {
        Write-Warning "Atualização concluída, mas os binários antigos ficaram em: $Previous"
    }
    Write-Host "Atualização concluída. Dados pessoais e inicialização preservados. Backup: $SavedBackup"
} catch {
    $Failure = $_
    $FailedBinaries = Join-Path $SavedBackup 'failed-binaries'
    New-Item -ItemType Directory -Path $FailedBinaries -Force | Out-Null
    foreach ($Name in @('SunriseCast.exe', '_internal')) {
        $Old = Join-Path $Previous $Name
        if (Test-Path -LiteralPath $Old) {
            $Current = Join-Path $InstallPath $Name
            Assert-InRoot $Current $InstallPath
            if (Test-Path -LiteralPath $Current) {
                try {
                    Move-Path $Current (Join-Path $FailedBinaries $Name)
                } catch {
                    Write-Warning "Não foi possível arquivar binário parcial: $Current"
                }
            }
            Assert-InRoot $Old $InstallPath
            Move-Path $Old (Join-Path $InstallPath $Name)
        }
    }
    if (Test-Path -LiteralPath $Stage) {
        try { Remove-Item -LiteralPath $Stage -Recurse -Force } catch { Write-Warning "Staging preservado para inspeção: $Stage" }
    }
    if ((Test-Path -LiteralPath $Previous) -and -not (Get-ChildItem -LiteralPath $Previous -Force -ErrorAction SilentlyContinue)) {
        Remove-Item -LiteralPath $Previous -Force
    }
    throw $Failure
}
