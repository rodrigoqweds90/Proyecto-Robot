# Genera el instalador completo (installer\output\RobotControl-Setup.exe):
# primero empaqueta la app en un .exe con PyInstaller, luego lo envuelve en
# un instalador de verdad con Inno Setup (accesos directos, desinstalador,
# sin pedir permisos de administrador).
#
# Requiere Inno Setup 6 instalado (winget install JRSoftware.InnoSetup).
#
# Uso: abre PowerShell en esta carpeta y ejecuta:
#   .\build_installer.ps1

pip install -r requirements.txt
# --onedir (no --onefile): el modo "un solo archivo" crea un proceso lanzador
# sin ventana propia ademas del proceso con ventana -- el instalador no le
# puede pedir a ese lanzador que se cierre, y falla el cierre automatico al
# actualizar. En modo carpeta el .exe es el unico proceso, sin ese problema.
# --collect-data esptool: esptool trae archivos de datos propios (el "stub"
# que sube al ESP32 para flashear rapido) que PyInstaller no detecta solo;
# sin esto, "Subir firmware" fallaba en el .exe empaquetado con
# "Flasher stub data is missing" aunque funcionara bien corriendo el codigo
# fuente directo (ahi esptool encuentra esos archivos en el disco normal).
python -m PyInstaller --onedir --windowed --name RobotControl --icon assets\icon.ico --add-data "assets;assets" --add-data "firmware;firmware" --collect-data esptool main.py

$iscc = Get-ChildItem -Path "C:\Program Files*","$env:LOCALAPPDATA\Programs" -Filter "ISCC.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $iscc) {
    Write-Host "No se encontro Inno Setup. Instalalo con: winget install JRSoftware.InnoSetup"
    exit 1
}
& $iscc.FullName installer\RobotControl.iss

Write-Host ""
Write-Host "Listo: installer\output\RobotControl-Setup.exe - esto es lo que le mandas a la otra persona."
