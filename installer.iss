#pragma codepage 65001

#define AppName "مدیریت حقوق کترینگ"
#define AppVersion "1.9.0"
#define AppPublisher "Catering Payroll"
#define AppExeName "CateringPayroll.exe"

[Setup]
AppId={{21AA9CB8-4790-45D8-83C1-E6C3040FE97E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Catering Payroll
DefaultGroupName={#AppName}
OutputDir=output
OutputBaseFilename=CateringPayroll-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
Uninstallable=yes
CloseApplications=yes
RestartApplications=no
VersionInfoVersion=1.9.0.0
VersionInfoProductVersion=1.9.0
VersionInfoProductName={#AppName}

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  if not Exec(
    ExpandConstant('{sys}\taskkill.exe'),
    '/F /T /IM "{#AppExeName}"',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) then
  begin
    Result := 'Unable to close the running Catering Payroll app. Close it and retry.';
    Exit;
  end;

  if (ResultCode <> 0) and (ResultCode <> 128) then
  begin
    Result := 'Windows could not close CateringPayroll.exe. Close the app and retry.';
    Exit;
  end;

  Sleep(750);
end;

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
