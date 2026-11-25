; Instalador de Windows (Inno Setup 6).
; Lo compila generar_instalador.bat o GitHub Actions; la versión llega con /DVersion=x.y.z
;
; - Se instala para el usuario actual, sin pedir permisos de administrador.
; - Solo instala el PROGRAMA. Los datos del usuario están en %APPDATA%\SimuladorConan y ni la
;   instalación, ni las actualizaciones, ni la desinstalación los tocan.
; - Parámetro /RELAUNCH: lo usa el actualizador de la app para volver a abrirla al terminar.

#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{C71A5A23-E147-44A9-8EF0-6A56B0903A1E}
AppName=Simulador Detective Conan
AppVersion={#Version}
AppVerName=Simulador Detective Conan {#Version}
AppPublisher=Proyecto de fans (no oficial)
DefaultDirName={localappdata}\Programs\SimuladorConan
DefaultGroupName=Simulador Detective Conan
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\salida
OutputBaseFilename=SimuladorConan-Setup-{#Version}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icono.ico
CloseApplications=force
RestartApplications=no
UninstallDisplayName=Simulador Detective Conan
UninstallDisplayIcon={app}\SimuladorConan.exe

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "ca"; MessagesFile: "compiler:Languages\Catalan.isl"

[Tasks]
Name: "escritorio"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; una versión nueva sustituye el programa entero (nunca toca los datos del usuario)
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\datos"
Type: filesandordirs; Name: "{app}\idiomas"

[Files]
Source: "..\dist\SimuladorConan\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Simulador Detective Conan"; Filename: "{app}\SimuladorConan.exe"
Name: "{group}\{cm:UninstallProgram,Simulador Detective Conan}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Simulador Detective Conan"; Filename: "{app}\SimuladorConan.exe"; Tasks: escritorio

[Run]
; instalación normal: casilla «Abrir ahora» al final
Filename: "{app}\SimuladorConan.exe"; Description: "{cm:LaunchProgram,Simulador Detective Conan}"; Flags: nowait postinstall skipifsilent
; actualización silenciosa desde la app: se vuelve a abrir sola
Filename: "{app}\SimuladorConan.exe"; Flags: nowait; Check: Relanzar

[Code]
function Relanzar: Boolean;
var
  i: Integer;
begin
  Result := False;
  for i := 1 to ParamCount do
    if CompareText(ParamStr(i), '/RELAUNCH') = 0 then
      Result := True;
end;
