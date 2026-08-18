#define MyAppName "Quotex Vision AI"
#define MyAppVersion "5.3"
#define MyAppPublisher "Quotex Vision AI"
#define MyAppExeName "QuotexVisionAI.exe"

[Setup]
AppId={{B5D3D1C8-9B8E-4E4F-9E7E-6A6F9CE1C321}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Quotex Vision AI
DefaultGroupName={#MyAppName}
OutputDir=dist
OutputBaseFilename=QuotexVisionAI-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
UninstallDisplayName={#MyAppName}

[Files]
Source: "..\dist\QuotexVisionAI\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\dist\QuotexVisionAI-Worker\*"; DestDir: "{app}\worker"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Quotex Vision AI"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Quotex Vision AI"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Start Quotex Vision AI"; Flags: nowait postinstall skipifsilent
