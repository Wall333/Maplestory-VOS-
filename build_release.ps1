$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$version = (Get-Content -LiteralPath (Join-Path $projectRoot "VERSION") -Raw).Trim()
$buildRoot = Join-Path $projectRoot ".build-v2"
$distRoot = Join-Path $projectRoot ".dist-v2"
$releaseRoot = Join-Path $projectRoot "Releases"
$packageRoot = Join-Path $distRoot "Maplestory-VOS"
$unpackedPath = Join-Path $releaseRoot "Maplestory-VOS-v$version"
$archivePath = Join-Path $releaseRoot "Maplestory-VOS-v$version-Windows-x64.zip"

New-Item -ItemType Directory -Force -Path $buildRoot, $distRoot, $releaseRoot | Out-Null

python -m PyInstaller --noconfirm --clean --windowed `
    --name "Maplestory-VOS" `
    --distpath $distRoot `
    --workpath (Join-Path $buildRoot "work") `
    --specpath $buildRoot `
    --add-data "$(Join-Path $projectRoot 'assets');assets" `
    (Join-Path $projectRoot "vos_bot.py")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Copy-Item -LiteralPath (Join-Path $projectRoot "config.json") -Destination $packageRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "README.md") -Destination $packageRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "VERSION") -Destination $packageRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "CHANGELOG.md") -Destination $packageRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "arduino_teensy_vos") -Destination $packageRoot -Recurse -Force

if (Test-Path -LiteralPath $unpackedPath) {
    throw "The unpacked release already exists at $unpackedPath. Move or remove it before rebuilding this version."
}
Copy-Item -LiteralPath $packageRoot -Destination $unpackedPath -Recurse

if (Test-Path -LiteralPath $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}
Compress-Archive -Path (Join-Path $unpackedPath "*") -DestinationPath $archivePath -CompressionLevel Optimal
Get-Item -LiteralPath (Join-Path $unpackedPath "Maplestory-VOS.exe") | Select-Object FullName, Length
Get-Item -LiteralPath $archivePath | Select-Object FullName, Length
