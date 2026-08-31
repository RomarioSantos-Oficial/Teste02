; ============================================================
;   Inno Setup Script - SectorFlow Overley Installer
; ============================================================
;   Este script gera um instalador .exe profissional para Windows.
;   Requisitos:
;     - Inno Setup 6+ instalado (https://jrsoftware.org/isinfo.php)
;     - Primeiro execute build_sectorflow.bat para gerar o EXE
; ============================================================

#define MyAppName "SectorFlow Overley"
#define MyAppVersion "0.0.6"
#define MyAppPublisher "Sector Flow"
#define MyAppURL "https://github.com/RomarioSantos-Oficial/Teste02"
#define MyAppExeName "SectorFlow.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-1234-56789ABCDEF0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppMutex=SectorFlow_ALFA_single_instance_v1
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousTasks=yes
UsePreviousLanguage=yes
AllowNoIcons=yes
DisableProgramGroupPage=yes
LicenseFile=
OutputDir=..\app
OutputBaseFilename=SectorFlow_Setup_{#MyAppVersion}
; O perfil ultra64/solid gerou um bloco LZMA2 corrompido ao extrair a DLL
; Qt6WebEngineCore.dll (aprox. 205 MB) em algumas máquinas. Um dicionário
; menor e arquivos comprimidos separadamente deixam a instalação verificável
; e evitam que uma falha em um bloco afete os arquivos seguintes.
Compression=lzma2/max
SolidCompression=no
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
SetupIconFile=..\images\logo\Logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
AppComments=Overlay de telemetria para Le Mans Ultimate (LMU)
VersionInfoVersion={#MyAppVersion}.0
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoDescription={#MyAppName} - Overlay de telemetria para LMU
; Requerimentos
MinVersion=10.0
PrivilegesRequired=lowest
; Visual
WizardSmallImageFile=..\images\logo\Logo.bmp
WindowVisible=no
WindowShowCaption=yes
WindowResizable=yes
CloseApplications=yes
RestartApplications=no
; Desinstalação
UninstallFilesDir={app}\uninstall

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"

[Files]
; Todos os arquivos abaixo são privados do SectorFlow. O ignoreversion garante
; que JSONs, traduções, imagens e DLLs sejam atualizados junto com o EXE.
Source: "..\dist\SectorFlow\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[InstallDelete]
; Remove atalhos antigos do Menu Iniciar nas atualizações. A partir da 0.0.5,
; o único atalho oferecido pelo instalador é o opcional da Área de Trabalho.
Type: files; Name: "{group}\{#MyAppName}.lnk"
Type: files; Name: "{group}\{cm:UninstallProgram,{#MyAppName}}.lnk"

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; IconIndex: 0; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "SOFTWARE\{#MyAppPublisher}\{#MyAppName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey

[Code]
function AppLanguageCode(): String;
begin
  if ActiveLanguage = 'english' then Result := 'en'
  else if ActiveLanguage = 'french' then Result := 'fr'
  else if ActiveLanguage = 'spanish' then Result := 'es'
  else if ActiveLanguage = 'italian' then Result := 'it'
  else if ActiveLanguage = 'german' then Result := 'de'
  else if ActiveLanguage = 'chinesesimplified' then Result := 'zh_CN'
  else if ActiveLanguage = 'korean' then Result := 'ko'
  else if ActiveLanguage = 'polish' then Result := 'pl'
  else Result := 'pt_BR';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  LanguageDir, LanguageFile, Json: String;
begin
  if CurStep = ssPostInstall then
  begin
    LanguageDir := ExpandConstant('{localappdata}\SectorFlow');
    LanguageFile := LanguageDir + '\language.json';
    if not FileExists(LanguageFile) then
    begin
      ForceDirectories(LanguageDir);
      Json := '{"language": "' + AppLanguageCode() + '"}';
      SaveStringToFile(LanguageFile, Json, False);
    end;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpWelcome then
    WizardForm.Caption := '{#MyAppName} - Instalador';
end;

procedure InitializeWizard();
begin
  WizardForm.WizardSmallBitmapImage.Visible := False;
end;
