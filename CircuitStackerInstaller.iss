#define MyAppName "Circuit Stacker"
#define MyAppVersion "1.6.3"
#define MyAppPublisher "Circuit Stacker"
#define MyAppExeName "CircuitStackers.exe"

[Setup]
AppId={{8C8AC8AE-6458-4C93-92D2-6C9BA8A70F77}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=CircuitStackerSetup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "dist\CircuitStackers\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  DataDirPage: TInputDirWizardPage;

procedure InitializeWizard;
begin
  DataDirPage :=
    CreateInputDirPage(
      wpSelectDir,
      'Save Data Location',
      'Choose where Circuit Stacker should store saves and settings.',
      'This folder will hold your career saves, world databases, and settings files.',
      False,
      ''
    );
  DataDirPage.Add('');
  DataDirPage.Values[0] := ExpandConstant('{localappdata}\Circuit Stackers');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DataRootPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    DataRootPath := Trim(DataDirPage.Values[0]);
    if DataRootPath <> '' then
    begin
      ForceDirectories(DataRootPath);
      SaveStringToFile(ExpandConstant('{app}\data_root.txt'), DataRootPath, False);
    end;
  end;
end;
