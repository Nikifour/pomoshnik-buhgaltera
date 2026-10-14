; Установщик «Помощник Бухгалтера» (Inno Setup 6).
; Собирается командой build_installer.bat или в GitHub Actions:
;   iscc /DAppVersion=1.2.3 /DExeSource=..\dist\Pomoshnik-Buhgaltera.exe installer\setup.iss
;
; Программа ставится в профиль пользователя (%LOCALAPPDATA%\Programs) без прав администратора:
; туда можно писать, поэтому работают автообновление и папка data рядом с программой.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef ExeSource
  #define ExeSource "..\dist\Pomoshnik-Buhgaltera.exe"
#endif

#define AppName "Помощник Бухгалтера"
#define AppExe "Помощник Бухгалтера.exe"

[Setup]
AppId={{D6795687-D964-439E-A82C-0343C4F2713D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
DefaultDirName={localappdata}\Programs\Pomoshnik-Buhgaltera
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Pomoshnik-Buhgaltera-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
CloseApplications=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать значок на рабочем столе"; GroupDescription: "Дополнительно:"
Name: "assoc"; Description: "Открывать файлы настроек (.pbsettings) этой программой"; GroupDescription: "Дополнительно:"

[Files]
Source: "{#ExeSource}"; DestDir: "{app}"; DestName: "{#AppExe}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; ассоциация .pbsettings (в HKCU — права администратора не нужны)
Root: HKA; Subkey: "Software\Classes\.pbsettings"; ValueType: string; ValueName: ""; ValueData: "PomoshnikBuhgaltera.Settings"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\PomoshnikBuhgaltera.Settings"; ValueType: string; ValueName: ""; ValueData: "Настройки «{#AppName}»"; Flags: uninsdeletekey; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\PomoshnikBuhgaltera.Settings\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\PomoshnikBuhgaltera.Settings\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assoc

[Run]
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; папку data (настройки, логотипы, печать) не удаляем — её спросим отдельно

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and DirExists(ExpandConstant('{app}\data')) then
    // SuppressibleMsgBox: при тихом удалении (/SUPPRESSMSGBOXES) ответ «Нет» — настройки сохраняются
    if SuppressibleMsgBox('Удалить также настройки программы (логотипы, печать, контакты, нумерацию КП)?' + #13#10 +
              'Если планируете установить программу снова — нажмите «Нет».',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      DelTree(ExpandConstant('{app}\data'), True, True, True);
end;
