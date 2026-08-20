; ============================================================
;   DICK 安装程序（Inno Setup 6）
;   把 DICK-HTML 便携文件夹打包成标准安装包：
;     - 用户双击安装 → 一路下一步
;     - 自动解压到安装目录
;     - 桌面 + 开始菜单快捷方式
;     - 注册 .codex 文件关联（可选，安装时默认勾选）
;   编译：ISCC.exe DICK_Setup.iss
; ============================================================

#define MyAppName "Direct-Interface Cork-bore Kit"
#define MyAppVersion "2.0"
#define MyAppExeName "DICK-HTML.exe"
#define MyAppPublisher "DICK"

[Setup]
AppId={{8E3F2A91-4D49-432E-9A1F-7A8B9C0D1E2F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\DICK
DefaultGroupName=DICK
DisableProgramGroupPage=yes
OutputDir=..\dist\release
OutputBaseFilename=DICK-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 关闭"是否安装到 Program Files"的 UAC 疑虑：装到用户目录更符合便携理念
PrivilegesRequired=lowest
; 数据目录跟随 exe（便携），安装目录可写
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
; 用默认英文 + 下方 [Messages] 中文覆盖关键文案（无需外部 .isl，完全自包含）
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
; ---- 安装向导中文界面（覆盖关键按钮/标题，其余保持默认） ----
WelcomeLabel1=欢迎安装 DICK（Direct-Interface Cork-bore Kit）
WelcomeLabel2=这是一款本地 AI 角色扮演聊天软件：免费、数据在你电脑上、无需注册。%n%n点击「下一步」继续，安装后桌面会出现 DICK 快捷方式。
SelectDirLabel3=选择安装位置
SelectDirBrowseLabel=点击「下一步」继续，将安装到以下文件夹。%n%n点击「下一步」继续。
SelectTasksLabel2=请选择要执行的附加任务，然后点击「下一步」。
ReadyLabel1=准备安装
ReadyLabel2a=点击「安装」开始安装 DICK。
InstallingLabel=正在安装 DICK，请稍候…
FinishedHeadingLabel=安装完成
FinishedLabel=已成功安装 DICK。%n%n点击「完成」退出安装向导。
ClickFinish=点击「完成」退出安装向导。
BeveledLabel=Direct-Interface Cork-bore Kit
ButtonNext=下一步 >
ButtonInstall=安装
ButtonFinish=完成
ButtonCancel=取消
ButtonBack=< 上一步
ButtonWizardBrowse=浏览…
ButtonYes=是(&Y)
ButtonNo=否(&N)
BrowseDialogTitle=选择文件夹
BrowseDialogLabel=请选择安装 DICK 的文件夹。
DiskSpaceMBLabel=至少需要 %1 MB 磁盘空间。
WizardSelectDir=选择安装位置
WizardSelectProgramGroup=选择开始菜单文件夹
WizardReady=准备安装
WizardInstalling=正在安装
ExitSetupMessage=安装尚未完成。%n%n确定要退出吗？
NoUninstallWarning=将卸载 DICK。%n%n确定要卸载吗？
ConfirmUninstall=确定要完全卸载 DICK 及其所有组件吗？
UninstallStatusLabel=正在卸载 DICK，请稍候…


[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: checkedonce
Name: "codexassoc"; Description: "关联 .codex 文件（双击用 DICK 打开）"; GroupDescription: "附加任务："; Flags: checkedonce

[Files]
; 整个 DICK-HTML 文件夹（递归）→ 安装到 {app}
Source: "..\DICK-HTML\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\DICK"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\DICK"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; .codex 文件关联（安装时勾选才写入，HKCU 无需管理员）
Root: HKCU; Subkey: "Software\Classes\.codex"; ValueType: string; ValueName: ""; ValueData: "DICK.Codex"; Tasks: codexassoc; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\DICK.Codex\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: codexassoc; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\DICK.Codex\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: codexassoc; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 DICK"; Flags: nowait postinstall skipifsilent
