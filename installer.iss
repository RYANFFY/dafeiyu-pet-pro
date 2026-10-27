; 大肥鱼桌宠 · Windows 安装包脚本（Inno Setup 6）
; 编译：ISCC.exe /DMyAppVersion=1.1.6 installer.iss
; 产物：dist\大肥鱼桌宠-安装版-v1.1.6.exe
;
; 2026-10-27 加：**检测旧版 → 问要不要先卸载 → 卸完装回原目录**。
; 主人的要求：「如果用户电脑上有旧版的桌宠，双击安装包后会给用户删除旧桌宠的选项，
; 然后删除后再在原目录下安装新版，用户不用删除重新配置 api 这些」。
;
; 为什么配置不会丢：打包版的 config.json 在
;   %APPDATA%\大肥鱼桌宠\config.json
; （见 桌宠.py 里 `if getattr(sys, "frozen", False)` 那段），**不在安装目录**里。
; 卸载器只删 {app}，所以 API Key / 设置 / 聊天记忆都原样留着。

#define MyAppName "大肥鱼桌宠"
#define MyAppExeName "大肥鱼桌宠.exe"
#define MyAppPublisher "RYANFFY"
#define MyAppURL "https://github.com/RYANFFY/deepseek-dafeiyu-pet"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
; 中文语言包：优先用 Inno 自带的 Languages 目录；找不到就用老机器上那份；
; 都没有就退回英文向导（不阻断编译）。
#define MyLangFile ""
#if FileExists(AddBackslash(CompilerPath) + "Languages\ChineseSimplified.isl")
  #define MyLangFile AddBackslash(CompilerPath) + "Languages\ChineseSimplified.isl"
#elif FileExists("F:\Codex\tools\innosetup-lang\ChineseSimplified.isl")
  #define MyLangFile "F:\Codex\tools\innosetup-lang\ChineseSimplified.isl"
#endif

[Setup]
AppId={{8F3A6D1C-2E44-4F0B-9C77-2A5B7E9D1C31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoDescription={#MyAppName} 安装程序
DefaultDirName={localappdata}\Programs\大肥鱼桌宠
; 升级时默认沿用上次装的目录（我们还会在 [Code] 里再强制一次）
UsePreviousAppDir=yes
DefaultGroupName=大肥鱼桌宠
DisableProgramGroupPage=no
DisableDirPage=no
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=大肥鱼桌宠-安装版-v{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ShowLanguageDialog=no
; 装之前先把正在跑的桌宠关掉（不然文件被占用，覆盖会失败）
CloseApplications=yes
RestartApplications=no

[Languages]
#if MyLangFile != ""
Name: "cn"; MessagesFile: "{#MyLangFile}"
#else
Name: "en"; MessagesFile: "compiler:Default.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："
Name: "startmenu"; Description: "创建开始菜单快捷方式"; GroupDescription: "附加任务："

[Files]
; 目录版（onedir）：整个文件夹装进去（含 _internal 那一堆依赖）。
Source: "dist\大肥鱼桌宠\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\大肥鱼桌宠"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenu
Name: "{autodesktop}\大肥鱼桌宠"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立刻运行大肥鱼桌宠"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; ⚠️ 只删安装目录。%APPDATA%\大肥鱼桌宠（配置 / Key / 聊天记忆）**故意不删** ——
; 卸载重装、升级都不该让用户重新配一遍。
Name: "{app}"; Type: filesandordirs

[Code]
const
  UNINST_ROOT = 'Software\Microsoft\Windows\CurrentVersion\Uninstall';
  OUR_APPID   = '{8F3A6D1C-2E44-4F0B-9C77-2A5B7E9D1C31}_is1';

var
  OldFound: Boolean;
  OldDir: String;
  OldVer: String;
  OldUninst: String;
  DoUninstallOld: Boolean;

{ 先声明一下（实现在下面「删目录前的安全闸」那节）：检测时就要用它验目录 }
function LooksLikeOurInstall(const Dir: String): Boolean; forward;

{ ---------- 找旧版 ---------- }

{ 从某个卸载键里读「是不是我们」+ 位置 / 版本 / 卸载命令 }
function TryReadEntry(Root: Integer; const SubKey: String;
                      var Dir, Ver, Uninst: String): Boolean;
var
  dn: String;
begin
  Result := False;
  if not RegQueryStringValue(Root, SubKey, 'DisplayName', dn) then
    Exit;
  { 认两个特征：AppId 对得上，或者显示名里带「大肥鱼」 }
  if (Pos('大肥鱼', dn) = 0) and (Pos(OUR_APPID, SubKey) = 0) then
    Exit;
  if not RegQueryStringValue(Root, SubKey, 'InstallLocation', Dir) then
    Dir := '';
  if not RegQueryStringValue(Root, SubKey, 'DisplayVersion', Ver) then
    Ver := '';
  if not RegQueryStringValue(Root, SubKey, 'UninstallString', Uninst) then
    Uninst := '';
  { 位置读不到就按默认目录猜（老版本可能没写 InstallLocation） }
  if Dir = '' then
    Dir := ExpandConstant('{localappdata}\Programs\大肥鱼桌宠');
  { ⚠️ 第 53 轮审查：光凭"显示名里有大肥鱼"就信这个路径太危险 ——
    注册表里写歪一个 `D:\` 就会把整个盘当旧版目录。这里再加一道：
    目录里得真有我们的 exe / unins000 / _internal，否则这个键不认。 }
  if not LooksLikeOurInstall(Dir) then
  begin
    Dir := '';
    Exit;
  end;
  Result := DirExists(Dir);
end;

procedure DetectOldInstall();
var
  Names: TArrayOfString;
  i: Integer;
  Sub, D, V, U: String;
begin
  OldFound := False;
  OldDir := '';
  OldVer := '';
  OldUninst := '';

  { 1) 先看我们自己那个 AppId（最准） }
  if TryReadEntry(HKCU, UNINST_ROOT + '\' + OUR_APPID, OldDir, OldVer, OldUninst) then
  begin
    OldFound := True;
    Exit;
  end;
  if TryReadEntry(HKLM, UNINST_ROOT + '\' + OUR_APPID, OldDir, OldVer, OldUninst) then
  begin
    OldFound := True;
    Exit;
  end;

  { 2) AppId 变了（更老的安装包）→ 在卸载列表里按显示名找 }
  if RegGetSubkeyNames(HKCU, UNINST_ROOT, Names) then
  begin
    for i := 0 to GetArrayLength(Names) - 1 do
    begin
      Sub := UNINST_ROOT + '\' + Names[i];
      if TryReadEntry(HKCU, Sub, D, V, U) then
      begin
        OldFound := True; OldDir := D; OldVer := V; OldUninst := U;
        Exit;
      end;
    end;
  end;
  if RegGetSubkeyNames(HKLM, UNINST_ROOT, Names) then
  begin
    for i := 0 to GetArrayLength(Names) - 1 do
    begin
      Sub := UNINST_ROOT + '\' + Names[i];
      if TryReadEntry(HKLM, Sub, D, V, U) then
      begin
        OldFound := True; OldDir := D; OldVer := V; OldUninst := U;
        Exit;
      end;
    end;
  end;

  { 3) 注册表里没有，但默认目录里躺着我们的 exe → 也算旧版（绿色版 / 手工装过） }
  if FileExists(ExpandConstant('{localappdata}\Programs\大肥鱼桌宠\{#MyAppExeName}')) then
  begin
    OldFound := True;
    OldDir := ExpandConstant('{localappdata}\Programs\大肥鱼桌宠');
    OldVer := '（未知版本）';
    OldUninst := '';
  end;
end;

{ ---------- 装之前：问一句 ---------- }
function InitializeSetup(): Boolean;
var
  R: Integer;
begin
  Result := True;
  DoUninstallOld := False;
  DetectOldInstall();
  if not OldFound then
    Exit;

  R := MsgBox('检测到你电脑上已经装了旧版桌宠：' + #13#10#13#10 +
              '    版本：' + OldVer + #13#10 +
              '    位置：' + OldDir + #13#10#13#10 +
              '要先卸载旧版，再把新版装回这个位置吗？' + #13#10#13#10 +
              '· 你的 API Key、设置、聊天记忆存在系统用户目录里，' + #13#10 +
              '  卸载旧版不会碰它们，不用重新配。' + #13#10#13#10 +
              '「是」= 先卸载旧版再原地装新版（推荐）' + #13#10 +
              '「否」= 不卸载，直接覆盖安装（可能残留旧文件）' + #13#10 +
              '「取消」= 退出安装',
              mbConfirmation, MB_YESNOCANCEL);
  if R = IDCANCEL then
    Result := False
  else if R = IDYES then
    DoUninstallOld := True;
end;

{ 目录页默认填旧版那个位置（卸载之后注册表就没了，所以现在就定下来）
  ⚠️ 命令行给了 /DIR 就别覆盖它。
  第 53 轮审查指出：原来靠"目录框是否等于默认值"猜有没有传 /DIR ——
  用户明确传的路径刚好等于默认值时猜不出来。改成**直接看命令行有没有 /DIR=**。 }
function DirParamGiven(): Boolean;
var
  S: String;
begin
  S := ExpandConstant('{param:DIR|}');
  Result := (S <> '') or (Pos('/DIR=', Uppercase(GetCmdTail)) > 0);
end;

procedure InitializeWizard();
begin
  if not (OldFound and (OldDir <> '')) then
    Exit;
  if DirParamGiven() then
    Exit;                            { 命令行说了算 }
  WizardForm.DirEdit.Text := OldDir;
end;

{ ---------- 删目录前的安全闸 ---------- }
function CountChar(const S: String; C: Char): Integer;
var
  I: Integer;
begin
  Result := 0;
  for I := 1 to Length(S) do
    if S[I] = C then
      Result := Result + 1;
end;

{ 这些"位置本身"绝对不能删（子目录另说） }
function IsForbiddenDir(const D: String): Boolean;
var
  List: array of String;
  I: Integer;
  X: String;
begin
  Result := False;
  X := RemoveBackslashUnlessRoot(Uppercase(D));
  SetArrayLength(List, 10);
  List[0] := ExpandConstant('{sd}\');
  List[1] := ExpandConstant('{win}');
  List[2] := ExpandConstant('{sys}');
  List[3] := ExpandConstant('{userprofile}');
  List[4] := ExpandConstant('{userdocs}');
  List[5] := ExpandConstant('{userdesktop}');
  List[6] := ExpandConstant('{localappdata}');
  List[7] := ExpandConstant('{appdata}');
  List[8] := ExpandConstant('{autopf}');
  List[9] := ExpandConstant('{tmp}');
  for I := 0 to GetArrayLength(List) - 1 do
  begin
    if List[I] = '' then
      Continue;
    if X = RemoveBackslashUnlessRoot(Uppercase(List[I])) then
    begin
      Result := True;
      Exit;
    end;
  end;
end;

{ 这个目录里到底有没有我们的东西 }
function LooksLikeOurInstall(const Dir: String): Boolean;
var
  D: String;
begin
  D := AddBackslash(Dir);
  Result := FileExists(D + '{#MyAppExeName}')
         or FileExists(D + 'unins000.exe')
         or DirExists(D + '_internal');
end;

{ 删之前必须过的一关：不能是盘根 / 系统目录，而且里面得有我们的文件。
  ⚠️ 别用"路径层级太浅就拒"这种规则 —— 装在 `D:\大肥鱼桌宠` 是很正常的，
  一刀切会把正当安装也挡掉（实测差点把自己坑了）。真正靠得住的是最后那条：
  **目录里必须有大肥鱼桌宠.exe / unins000.exe / _internal**。 }
function IsSafeToDeleteDir(const Dir: String): Boolean;
var
  D: String;
begin
  Result := False;
  D := RemoveBackslashUnlessRoot(Trim(Dir));
  if Length(D) < 4 then                       { C:\x 最少 4 个字符 }
    Exit;
  if (Length(D) = 3) and (D[2] = ':') then    { D:\ 这种盘根 }
    Exit;
  if CountChar(D, '\') < 1 then               { 盘根下面至少得有一层 }
    Exit;
  if IsForbiddenDir(D) then
    Exit;
  Result := LooksLikeOurInstall(D);
end;

{ 旧版目录：能安全删才删，删不了就中止安装（绝不瞎删） }
function RemoveOldDirSafely(const Dir: String; var ErrMsg: String): Boolean;
begin
  Result := False;
  if not IsSafeToDeleteDir(Dir) then
  begin
    ErrMsg := '旧版装在：' + Dir + #13#10#13#10 +
              '这个位置我不敢直接删（怕误删别的东西）。' + #13#10 +
              '请先用旧版自己的卸载程序手动卸掉，再重新运行这个安装包。';
    Exit;
  end;
  Result := DelTree(Dir, True, True, True);
  if not Result then
    ErrMsg := '旧版目录删不掉：' + Dir + #13#10#13#10 +
              '可能有文件被占用。请关掉桌宠 / 重启后再试，或手动卸载旧版。';
end;

{ ---------- 真正开工前：关掉正在跑的 + 卸载旧版 ---------- }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  R: Integer;
  UninstExe: String;
  ErrMsg: String;
begin
  Result := '';
  NeedsRestart := False;

  { 桌宠是单实例、而且会占着 exe / _internal 里的文件 —— 不关掉覆盖会失败 }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM "{#MyAppExeName}"',
       '', SW_HIDE, ewWaitUntilTerminated, R);

  if not DoUninstallOld then
    Exit;

  { 有卸载器：跑它；跑不起来就**中止**，不再自己删目录
    （第 53 轮审查：原来卸载失败会 DelTree，路径要是读歪了就删错东西） }
  if OldUninst <> '' then
  begin
    UninstExe := RemoveQuotes(OldUninst);
    if FileExists(UninstExe) then
    begin
      if Exec(UninstExe, '/SILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_SHOW,
              ewWaitUntilTerminated, R) then
        Exit;                        { 卸载器跑完了，接着装 }
      Result := '旧版卸载程序没能正常运行。' + #13#10#13#10 +
                '请先手动卸载旧版（设置 → 应用 → 大肥鱼桌宠），再重新运行这个安装包。';
      Exit;
    end;
  end;

  { 没有卸载器（绿色版 / 注册表残缺）：**过安全闸**才敢删 }
  if RemoveOldDirSafely(OldDir, ErrMsg) then
    Exit;
  Result := ErrMsg;
end;
