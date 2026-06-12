#define MyAppName "Voice 1C"
#define MyAppVersion "1.1.3"
#define MyAppPublisher "xerlovemate"
#define MyAppExeName "Voice1C.exe"

[Setup]
AppId={{A47A6E92-782C-4E93-8E0E-AC1C00000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Voice 1C
DefaultGroupName=Voice 1C
AllowNoIcons=yes
LicenseFile=
OutputDir=..\dist_installer
OutputBaseFilename=Voice1CSetup
SetupIconFile=..\resources\icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные ярлыки:"; Flags: unchecked

[Files]
Source: "..\dist\Voice1C\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Voice 1C"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\Voice 1C"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить Voice 1C"; Flags: nowait postinstall skipifsilent
