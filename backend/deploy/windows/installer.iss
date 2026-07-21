; Inno Setup script for Question Bank (Windows desktop / tray app).
;
; Produces a friendly GUI installer: double-click -> UAC -> Next/Install/Finish.
; It installs the app to Program Files, adds a login autostart entry so the
; tray icon appears after every sign-in, and creates Start Menu shortcuts.
; Uninstall (via Windows "Apps") closes the tray, removes the autostart entry
; and any firewall rule; application data in %APPDATA%\QuestionBank is preserved.
;
; Local-network sharing is OFF by default and is toggled from the tray menu
; (which adds/removes the firewall rule on demand) -- the installer no longer
; opens the firewall or installs a background service.
;
; Compiled in CI with:
;   iscc /DMyAppVersion=<ver> /DPayloadDir=<staged files> /O<out dir> installer.iss
; PayloadDir must contain: question-bank.exe (+ optional README.txt).

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
#ifndef PayloadDir
  #define PayloadDir "."
#endif

#define MyAppName "Question Bank"
#define MyAppExe "question-bank.exe"
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
UninstallDisplayIcon={app}\{#MyAppExe}
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

[Tasks]
Name: "autostart"; Description: "开机自动启动题库(登录时显示托盘图标)"; GroupDescription: "启动选项:"
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[INI]
; Internet shortcut used by the Start Menu "open" icon (opens the running app).
Filename: "{app}\QuestionBank.url"; Section: "InternetShortcut"; Key: "URL"; String: "http://localhost:{#MyPort}/"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\打开题库"; Filename: "{app}\QuestionBank.url"
Name: "{group}\卸载题库"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
; Login autostart for all users (single-PC server model). Removed on uninstall.
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "QuestionBank"; ValueData: """{app}\{#MyAppExe}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; Launch the tray now (as the signed-in user, not the elevated installer).
Filename: "{app}\{#MyAppExe}"; Description: "立即启动题库"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
; Close the running tray so its files can be removed, and drop any firewall rule.
Filename: "{sys}\taskkill.exe"; Parameters: "/im {#MyAppExe} /f"; Flags: runhidden; RunOnceId: "StopTray"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#MyFwRule}"""; Flags: runhidden; RunOnceId: "RemoveFirewall"

[UninstallDelete]
Type: files; Name: "{app}\QuestionBank.url"

[Code]
{ Close any running tray instance before copying files, otherwise the running
  executable would be locked and the upgrade would fail. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/im {#MyAppExe} /f', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;
