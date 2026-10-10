; Inno Setup script. Build: iscc /DAppVersion=0.1.0 packaging\windows\installer.iss
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6F0C2E52-9D7B-4C55-9B7E-3E0B5A0F7A11}
AppName=RawTag
AppVersion={#AppVersion}
AppPublisher=RawTag
DefaultDirName={autopf}\RawTag
DefaultGroupName=RawTag
DisableProgramGroupPage=yes
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=RawTag-{#AppVersion}-windows-x64-setup
SetupIconFile=..\..\build\icon.ico
UninstallDisplayIcon={app}\RawTag.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\RawTag\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\RawTag"; Filename: "{app}\RawTag.exe"
Name: "{autodesktop}\RawTag"; Filename: "{app}\RawTag.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\RawTag.exe"; Description: "{cm:LaunchProgram,RawTag}"; Flags: nowait postinstall skipifsilent
