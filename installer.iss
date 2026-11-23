; Bo cai Windows (Inno Setup 6). CI: ISCC /DAppVersion=1.2.3 installer.iss -> dist\MasterDownloader-Setup.exe
#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

[Setup]
; AppId co dinh: doi la Windows coi nhu app khac, ban cu khong duoc nang cap
AppId={{8A362CF2-4A9D-495E-9E92-4420B739C801}
AppName=MasterDownloader
AppVersion={#AppVersion}
AppPublisher=thientrile
AppPublisherURL=https://github.com/thientrile/MasterDownloader-releases
; Cai theo nguoi dung, khong UAC: updater chay Setup moi ma khong can quyen admin
PrivilegesRequired=lowest
DefaultDirName={userpf}\MasterDownloader
DefaultGroupName=MasterDownloader
DisableProgramGroupPage=yes
; Nguoi dung phai dong y dieu khoan khi cai (ban im lang tu dong y)
LicenseFile=TERMS.txt
UninstallDisplayIcon={app}\MasterDownloader.exe
OutputDir=dist
OutputBaseFilename=MasterDownloader-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
; Inno khong kem san ban dich tieng Viet (chi co ban khong chinh thuc), nen dung tieng Anh
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\MasterDownloader.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "TERMS.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\THIRD_PARTY_LICENSES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MasterDownloader"; Filename: "{app}\MasterDownloader.exe"
Name: "{group}\{cm:UninstallProgram,MasterDownloader}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\MasterDownloader"; Filename: "{app}\MasterDownloader.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MasterDownloader.exe"; Description: "{cm:LaunchProgram,MasterDownloader}"; Flags: nowait postinstall skipifsilent
; Updater chay Setup /VERYSILENT /relaunch=1 -> mo lai app sau khi cai
Filename: "{app}\MasterDownloader.exe"; Flags: nowait; Check: IsRelaunch

; Go cai dat chi xoa file da cai; du lieu o %APPDATA%\MasterDownloader duoc giu lai

[Code]
function IsRelaunch: Boolean;
begin
  Result := ExpandConstant('{param:relaunch|0}') = '1';
end;
