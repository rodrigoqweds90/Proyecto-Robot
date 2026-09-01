# Compila el firmware con PlatformIO y copia los .bin a app\firmware\, para
# que el boton "Subir firmware" de la app de escritorio siempre mande la
# ultima version de src\main.cpp. Correr esto despues de cada cambio al firmware.
#
# Uso: abre PowerShell en esta carpeta y ejecuta:
#   .\sync_firmware.ps1

$pio = "$env:USERPROFILE\.platformio\penv\Scripts\pio.exe"
& $pio run -d $PSScriptRoot

$origen = Join-Path $PSScriptRoot ".pio\build\esp32dev"
$destino = Join-Path $PSScriptRoot "app\firmware"
New-Item -ItemType Directory -Force -Path $destino | Out-Null
Copy-Item (Join-Path $origen "bootloader.bin") (Join-Path $destino "bootloader.bin") -Force
Copy-Item (Join-Path $origen "partitions.bin") (Join-Path $destino "partitions.bin") -Force
Copy-Item (Join-Path $origen "firmware.bin") (Join-Path $destino "firmware.bin") -Force

Write-Host "Firmware sincronizado en app\firmware\"
