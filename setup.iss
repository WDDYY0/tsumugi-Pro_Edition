; ============================================================
; AI 扒谱工具 - Inno Setup 安装脚本 v2.2.1
; 快捷方式直接指向 pythonw.exe，无 VBS 中间层，最稳定
; ============================================================

#define MyAppName "AI 扒谱工具"
#define MyAppVersion "2.2.1"
#define MyAppPublisher "无端的乐音"
#define MyAppURL "https://github.com/anime-song/tsumugi"

[Setup]
AppId={{8F3A7C2E-4B5D-4A6F-9E8C-1D2E3F4A5B6C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={%USERPROFILE}\Apps\tsumugi
DefaultGroupName={#MyAppName}
AllowNoIcons=yes

DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
DisableReadyPage=no
DisableFinishedPage=no

LicenseFile=license.txt

OutputDir=installer
OutputBaseFilename=AI扒谱工具_安装程序_v{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes

PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

WizardStyle=modern
SetupIconFile=resources\tsumugi.ico
UninstallDisplayIcon={app}\resources\tsumugi.ico
UninstallDisplayName={#MyAppName}
MinVersion=10.0.17763

[Messages]
WelcomeLabel1=欢迎使用 {#MyAppName} 安装向导
WelcomeLabel2=即将在你的电脑上安装 {#MyAppName} 版本 {#MyAppVersion}。%n%n{#MyAppName} 是一款将音频自动转写为多轨 MIDI 的工具，支持任意乐器、三种转换模式、GPU 加速。%n%n点击“下一步”继续，或点击“取消”退出安装。%n%n建议在安装前关闭所有其他程序。
WizardSelectDir=选择安装位置
SelectDirDesc=请选择 {#MyAppName} 的安装位置。
SelectDirLabel3=安装程序将把 {#MyAppName} 安装到下面的文件夹中。%n%n点击“下一步”继续。如果你需要安装到其他位置，请点击“浏览”。
WizardSelectTasks=选择附加任务
SelectTasksDesc=请选择安装 {#MyAppName} 时需要执行的附加任务。
SelectTasksLabel2=请选择安装 {#MyAppName} 时需要执行的附加任务，然后点击“下一步”。%n%n建议勾选“创建桌面快捷方式”，这样你可以直接从桌面启动本软件。
WizardReady=准备安装
ReadyLabel1=安装程序已准备好开始安装 {#MyAppName} 到你的电脑。
ReadyLabel2a=点击“安装”开始安装，或点击“上一步”检查或更改设置。
ReadyLabel2b=点击“安装”开始安装。
WizardPreparing=正在准备安装
PreparingDesc=安装程序正在准备安装 {#MyAppName} 到你的电脑。
WizardInstalling=正在安装
InstallingLabel=安装程序正在安装 {#MyAppName} 到你的电脑，请稍候。
WizardFinished=安装完成
FinishedLabel=安装程序已完成 {#MyAppName} 的安装。%n%n点击“完成”关闭安装向导。%n%n首次启动软件时，会自动下载依赖库，约需 5-15 分钟，请耐心等待。
ClickFinish=点击“完成”关闭安装向导。
FinishedRestartLabel=要完成 {#MyAppName} 的安装，必须重启计算机。是否现在重启？
FinishedRestartMsg=要完成 {#MyAppName} 的安装，必须重启计算机。%n%n是否现在重启？
RunEntryExec=运行 %1
RunEntryShellExec=运行 %1

[Languages]
Name: "chinese"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: checkedonce

[Files]
Source: "*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: ".venv\*,__pycache__\*,_源备份\*,tests\*,evaluation\*,setup.iss,license.txt,compile_pyc.py,诊断图标.bat,installer\*"

[Icons]
Name: "{userdesktop}\AI 扒谱工具"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\tsumugi_gui_v2.py"""; WorkingDir: "{app}"; IconFilename: "{app}\resources\tsumugi.ico"; Comment: "AI 扒谱工具 v{#MyAppVersion}"; Tasks: desktopicon
Name: "{userprograms}\AI 扒谱工具"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\tsumugi_gui_v2.py"""; WorkingDir: "{app}"; IconFilename: "{app}\resources\tsumugi.ico"
Name: "{userprograms}\AI 扒谱工具（排查模式）"; Filename: "{app}\一键使用\0-启动图形界面.bat"; WorkingDir: "{app}"; IconFilename: "{app}\resources\tsumugi.ico"
Name: "{userprograms}\卸载 AI 扒谱工具"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\安装.bat"; Description: "初始化环境（首次安装约 5-15 分钟）"; Flags: postinstall waituntilterminated

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function InitializeSetup(): Boolean;
var
  Version: TWindowsVersion;
  ErrorMsg: String;
begin
  GetWindowsVersionEx(Version);

  if Version.Major < 10 then
  begin
    ErrorMsg := '⚠️ 系统版本过低，无法安装！' + #13#10 + #13#10 + '本软件需要 Windows 10 或 Windows 11 系统。';
    MsgBox(ErrorMsg, mbError, MB_OK);
    Result := False;
    Exit;
  end;

  if (Version.Major = 10) and (Version.Minor = 0) and (Version.Build < 17763) then
  begin
    ErrorMsg := '⚠️ 系统版本过旧！' + #13#10 + #13#10 + '本软件需要 Windows 10 (1809) 或更高版本。';
    MsgBox(ErrorMsg, mbError, MB_OK);
    Result := False;
    Exit;
  end;

  Result := True;
end;