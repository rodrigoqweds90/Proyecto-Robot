# Compila el firmware (src\main.cpp) y copia los .bin a app\firmware\, para
# que el boton "Subir firmware" de la app de escritorio siempre mande la
# ultima version. Correr esto despues de cada cambio al firmware.
#
# Se compila con arduino-cli (el que trae el Arduino IDE) y el paquete de
# placas de Bluepad32 (esp32-bluepad32:esp32), no con PlatformIO: Bluepad32
# para PlatformIO necesita pioarduino, que rompe el entorno de PlatformIO
# (ver el vault, "Bluetooth del mando"). Particion "No OTA": 2 MB de programa
# (WiFi + Bluetooth no entran en 1.2 MB); la memoria con la pose de Inicio
# queda en el mismo lugar, no se pierde.
#
# Uso: abre PowerShell en esta carpeta y ejecuta:
#   .\sync_firmware.ps1            (compila y copia a app\firmware\)
#   .\sync_firmware.ps1 -Subir COM4 (ademas lo sube al ESP32 de ese puerto)
param([string]$Subir = "")

$cli = "$env:LOCALAPPDATA\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"
$placa = "esp32-bluepad32:esp32:esp32:PartitionScheme=no_ota"

# arduino-cli compila carpetas de sketch: se arma una con una copia de src\main.cpp
$sketch = Join-Path $PSScriptRoot "build_arduino\RobotFirmware"
$salida = Join-Path $PSScriptRoot "build_arduino\salida"
New-Item -ItemType Directory -Force -Path $sketch, $salida | Out-Null
Copy-Item (Join-Path $PSScriptRoot "src\main.cpp") (Join-Path $sketch "main.cpp") -Force
Set-Content -Path (Join-Path $sketch "RobotFirmware.ino") -Value "// El codigo esta en main.cpp (copia de src\main.cpp hecha por sync_firmware.ps1)"

& $cli compile --fqbn $placa --output-dir $salida $sketch
if ($LASTEXITCODE -ne 0) { Write-Host "Fallo la compilacion."; exit 1 }

$destino = Join-Path $PSScriptRoot "app\firmware"
New-Item -ItemType Directory -Force -Path $destino | Out-Null
Copy-Item (Join-Path $salida "RobotFirmware.ino.bootloader.bin") (Join-Path $destino "bootloader.bin") -Force
Copy-Item (Join-Path $salida "RobotFirmware.ino.partitions.bin") (Join-Path $destino "partitions.bin") -Force
Copy-Item (Join-Path $salida "RobotFirmware.ino.bin") (Join-Path $destino "firmware.bin") -Force
Write-Host "Firmware sincronizado en app\firmware\"

if ($Subir) {
    & $cli upload --fqbn $placa -p $Subir --input-dir $salida $sketch
}
