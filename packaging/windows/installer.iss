; Inno Setup script. Build: iscc /DAppVersion=0.1.0 packaging\windows\installer.iss
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6F0C2E52-9D7B-4C55-9B7E-3E0B5A0F7A11}
AppName=Music Tag Editor
AppVersion={#AppVersion}
AppPublisher=Mido Reigh
DefaultDirName={autopf}\Music Tag Editor
DefaultGroupName=Music Tag Editor
DisableProgramGroupPage=yes
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=MusicTagEditor-{#AppVersion}-windows-x64-setup
SetupIconFile=..\..\build\icon.ico
UninstallDisplayIcon={app}\MusicTagEditor.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\MusicTagEditor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Music Tag Editor"; Filename: "{app}\MusicTagEditor.exe"
Name: "{autodesktop}\Music Tag Editor"; Filename: "{app}\MusicTagEditor.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MusicTagEditor.exe"; Description: "{cm:LaunchProgram,Music Tag Editor}"; Flags: nowait postinstall skipifsilent
