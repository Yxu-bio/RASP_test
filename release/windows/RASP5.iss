#ifndef StageDir
  #error StageDir must point to a completed RASP5 Windows stage.
#endif
#ifndef AppVersion
  #define AppVersion "5.0.0-dev.0"
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif

#define AppName "RASP5"
#define Publisher "RASP5 contributors"
#define ProjectUrl "https://github.com/Yxu-bio/RASP_test"

[Setup]
AppId={{7EA06936-E719-4EC8-9D3D-F5378335B7B1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
AppPublisherURL={#ProjectUrl}
AppSupportURL={#ProjectUrl}
AppUpdatesURL={#ProjectUrl}
DefaultDirName={localappdata}\Programs\RASP5
DefaultGroupName=RASP5
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=RASP5-{#AppVersion}-windows-x86_64-setup
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayName=RASP5 {#AppVersion}
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "{#SourcePath}\languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\RASP5-APPLICATION-MANIFEST.json"; DestDir: "{app}"; Flags: ignoreversion; AfterInstall: RelocateRuntime

[Icons]
Name: "{group}\RASP5"; Filename: "{app}\RASP5.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\runtime\python\pythonw.exe"; Flags: runminimized
Name: "{group}\RASP5 Debug Console"; Filename: "{app}\RASP5-debug.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\runtime\python\python.exe"
Name: "{autodesktop}\RASP5"; Filename: "{app}\RASP5.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\runtime\python\pythonw.exe"; Tasks: desktopicon; Flags: runminimized

[Run]
Filename: "{app}\RASP5.cmd"; WorkingDir: "{app}"; Description: "Launch RASP5"; Flags: nowait postinstall skipifsilent shellexec; Check: RelocationSucceeded

[UninstallDelete]
Type: files; Name: "{app}\runtime\python\.rasp5-unpacked"
Type: files; Name: "{app}\runtime\python\.rasp5-relocation-failed"

[Code]
var
  RelocationFailed: Boolean;

procedure RecordRelocationFailure(const MessageText: String; ResultCode: Integer);
var
  FailurePath: String;
begin
  RelocationFailed := True;
  FailurePath := ExpandConstant('{app}\runtime\python\.rasp5-relocation-failed');
  SaveStringToFile(FailurePath, IntToStr(ResultCode) + #13#10, False);
  SuppressibleMsgBox(
    MessageText + #13#10 +
      'RASP5 was copied, but its Python runtime is not ready. ' +
      'Starting RASP5 will retry initialization.',
    mbError,
    MB_OK,
    IDOK
  );
end;

procedure RelocateRuntime;
var
  PythonExe: String;
  UnpackScript: String;
  MarkerPath: String;
  ResultCode: Integer;
begin
  PythonExe := ExpandConstant('{app}\runtime\python\python.exe');
  UnpackScript := ExpandConstant('{app}\runtime\python\Scripts\conda-unpack-script.py');
  MarkerPath := ExpandConstant('{app}\runtime\python\.rasp5-unpacked');
  DeleteFile(MarkerPath);
  DeleteFile(ExpandConstant('{app}\runtime\python\.rasp5-relocation-failed'));
  if (not FileExists(PythonExe)) or (not FileExists(UnpackScript)) then begin
    RecordRelocationFailure('The bundled Python relocation command is missing.', -1);
    Exit;
  end;
  if not Exec(
    PythonExe,
    '-B "' + UnpackScript + '"',
    ExpandConstant('{app}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) then begin
    RecordRelocationFailure('Could not start the bundled Python relocation command.', -2);
    Exit;
  end;
  if ResultCode <> 0 then begin
    RecordRelocationFailure(
      Format('Bundled Python relocation failed with exit code %d.', [ResultCode]),
      ResultCode
    );
    Exit;
  end;
  if not SaveStringToFile(MarkerPath, '', False) then
    RecordRelocationFailure(
      'Bundled Python relocation completed, but its success marker could not be written.',
      -3
    );
end;

function RelocationSucceeded: Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\runtime\python\.rasp5-unpacked'));
end;

function GetCustomSetupExitCode: Integer;
begin
  if RelocationFailed then
    Result := 20
  else
    Result := 0;
end;
