; Inno Setup script for Question Bank (Windows intranet server).
;
; Produces a friendly GUI installer: double-click -> UAC -> Next/Install/Finish.
; It installs the app to Program Files, registers the bundled WinSW wrapper as an
; auto-start Windows service, opens the LAN firewall port and creates Start Menu
; shortcuts. Uninstall (via Windows "Apps") stops the service, removes it and the
; firewall rule; application data in C:\ProgramData\QuestionBank is preserved.
;
; Compiled in CI with:
;   iscc /DMyAppVersion=<ver> /DPayloadDir=<staged files> /O<out dir> installer.iss
; PayloadDir must contain: question-bank.exe, question-bank-service.exe,
; question-bank-service.xml (+ optional README.txt / *.ps1 advanced tools).

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
#ifndef PayloadDir
  #define PayloadDir "."
#endif

#define MyAppName "Question Bank"
#define MyServiceId "question-bank"
#define MyPort "8000"
#define MyFwRule "Question Bank (" + MyPort + ")"

[Setup]
AppId={{8F3A2B14-9C7E-4D6A-B1F2-3E5C7A9D0B11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=gygy-open
DefaultDirName={autopf}\QuestionBank
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\question-bank.exe
UninstallDisplayName={#MyAppName} {#MyAppVersion}
OutputBaseFilename=QuestionBank-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[INI]
; Internet shortcut used by the Start Menu "open" icon (no flashing console).
Filename: "{app}\QuestionBank.url"; Section: "InternetShortcut"; Key: "URL"; String: "http://localhost:{#MyPort}/"

[Icons]
Name: "{group}\打开题库"; Filename: "{app}\QuestionBank.url"
Name: "{group}\卸载题库"; Filename: "{uninstallexe}"

[Run]
; Open the firewall (delete-then-add to avoid duplicate rules on reinstall).
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#MyFwRule}"""; Flags: runhidden; StatusMsg: "配置防火墙..."
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#MyFwRule}"" dir=in action=allow protocol=TCP localport={#MyPort}"; Flags: runhidden; StatusMsg: "配置防火墙..."
; Register and start the background service.
Filename: "{app}\question-bank-service.exe"; Parameters: "install"; Flags: runhidden; StatusMsg: "注册后台服务..."
Filename: "{app}\question-bank-service.exe"; Parameters: "start"; Flags: runhidden; StatusMsg: "启动服务..."
; Offer to open the app in the browser at the end.
Filename: "http://localhost:{#MyPort}/"; Description: "立即打开题库(完成安装向导)"; Flags: postinstall shellexec skipifsilent nowait

[UninstallRun]
Filename: "{app}\question-bank-service.exe"; Parameters: "stop"; Flags: runhidden; RunOnceId: "StopService"
Filename: "{app}\question-bank-service.exe"; Parameters: "uninstall"; Flags: runhidden; RunOnceId: "RemoveService"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#MyFwRule}"""; Flags: runhidden; RunOnceId: "RemoveFirewall"

[UninstallDelete]
Type: files; Name: "{app}\QuestionBank.url"
; WinSW writes logs next to the wrapper; clean them up on uninstall.
Type: files; Name: "{app}\question-bank-service.*.log"
Type: files; Name: "{app}\question-bank-service.wrapper.log"

[Code]
{ Stop and remove any existing service before copying files, otherwise the
  running executable would be locked and the upgrade would fail. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\net.exe'), 'stop {#MyServiceId}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\sc.exe'), 'delete {#MyServiceId}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;
