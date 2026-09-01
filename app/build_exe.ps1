# Genera un unico archivo .exe (dist\RobotControl.exe) que se puede copiar
# y ejecutar en cualquier otra computadora con Windows, sin instalar Python.
#
# Uso: abre PowerShell en esta carpeta y ejecuta:
#   .\build_exe.ps1

pip install -r requirements.txt
pyinstaller --onefile --windowed --name RobotControl --icon assets\icon.ico --add-data "assets;assets" --add-data "firmware;firmware" --collect-data esptool main.py

Write-Host ""
Write-Host "Listo: dist\RobotControl.exe — copia solo ese archivo a la otra computadora."
