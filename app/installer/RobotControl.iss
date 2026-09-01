; SEGMENTO: INSTALADOR (Inno Setup)
; Empaqueta dist\RobotControl.exe (generado por build_exe.ps1) en un
; instalador de verdad: se instala una vez en una carpeta fija, deja acceso
; directo en el menu inicio, y aparece en "Agregar o quitar programas" para
; desinstalarlo limpio. No pide permisos de administrador (se instala solo
; para el usuario actual), asi no interrumpe con el aviso de Windows (UAC).
;
; Las poses/secuencias/config del usuario NO viven aqui -- se guardan en
; %APPDATA%\RobotControl (ver app/paths.py), asi que sobreviven a reinstalar
; o actualizar la app sin perder nada.

#define MyAppName "Robot Control"
#define MyAppVersion "1.0"
#define MyAppExeName "RobotControl.exe"

[Setup]
AppId={{B4D1E9C0-6A2F-4B8E-9C1A-8F2E7A5D3C90}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\RobotControl
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=RobotControl-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el Escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\dist\RobotControl\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName} ahora"; Flags: nowait postinstall skipifsilent
