; Inno Setup — instalador do Processador de Faturas de Energia.
; Compile com: build\build_installer.ps1  (ou ISCC.exe build\installer.iss)
; Instala por usuário (sem exigir administrador). Gera dist\FaturasDeEnergia-Setup.exe

#define MyAppName "Processador de Faturas de Energia"
#define MyAppShort "FaturasDeEnergia"
#define MyAppVersion "1.0.0"
#define MyAppExe "FaturasDeEnergia.exe"

; Pasta de origem (conteudo do PyInstaller). Pode ser sobrescrita pelo build via
; ISCC /DSrcDir=<caminho> para apontar ao build LOCAL (fora do Google Drive).
#ifndef SrcDir
  #define SrcDir "..\dist\FaturasDeEnergia"
#endif

[Setup]
AppId={{A7F3C9E2-5B41-4D8A-9E60-1C2D3E4F5A6B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=TJGO / UFG
DefaultDirName={autopf}\{#MyAppShort}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename={#MyAppShort}-Setup
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
; Conteúdo da pasta gerada pelo PyInstaller (one-folder).
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\Guia rápido (LEIA-ME)"; Filename: "{app}\LEIA-ME.txt"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Abrir o aplicativo agora"; Flags: nowait postinstall skipifsilent
