; ============================================================
;   Inno Setup Script - SectorFlow ALFA Installer
; ============================================================
;   Este script gera um instalador .exe profissional para Windows.
;   Requisitos:
;     - Inno Setup 6+ instalado (https://jrsoftware.org/isinfo.php)
;     - Primeiro execute build_sectorflow.bat para gerar o EXE
; ============================================================

#define MyAppName "SectorFlow ALFA"
#define MyAppVersion "0.0.1"
#define MyAppPublisher "Sector Flow"
#define MyAppURL "https://github.com/RomarioSantos-Oficial/Teste02"
#define MyAppExeName "SectorFlow.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-1234-56789ABCDEF0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=
OutputDir=..\app
OutputBaseFilename=SectorFlow_Setup_{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallModeIn64Mode=x64
SetupIconFile=..\images\logo\Logo.ico
UninstallDisplayIcon={app}\SectorFlow.exe
AppComments=Overlay de telemetria para Le Mans Ultimate (LMU)
AppContact=contact@example.com
; Requerimentos
MinVersion=10.0
PrivilegesRequired=lowest
; Visual
WizardSmallImageFile=..\images\logo\Logo.bmp
WindowVisible=no
WindowShowCaption=yes
WindowResizable=yes
; Desinstalação
UninstallFilesDir={app}\uninstall

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\SectorFlow\*"; DestDir: "{app}"; Flags: ignoreversion recursivesubdirs createallsubdirs
Source: "..\src\config\widgets.json"; DestDir: "{app}\src\config"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey

[Code]
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpWelcome then
    WizardForm.Caption := '{#MyAppName} - Instalador';
end;

procedure InitializeWizard();
begin
  WizardForm.WizardSmallBitmapImage.Visible := False;
end;
