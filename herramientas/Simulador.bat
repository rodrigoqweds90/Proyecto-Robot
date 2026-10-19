@echo off
rem Abre el simulador de caminata (solo lee las poses y secuencias de la app, no mueve el robot)
cd /d "%~dp0"
start "" "C:\Users\rodri\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe" visor_simulador.py
