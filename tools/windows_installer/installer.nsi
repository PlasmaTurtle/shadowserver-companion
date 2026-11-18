; Compile with build.py. Payload and uninstall inventory are generated together.
Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
!include "FileFunc.nsh"
!include "nsDialogs.nsh"

Var DataChoice
Var RetainDataRadio
Var FreshDataRadio
Var InstallGate
Var SetupInstance
Var UpdateRequested
Var RestartRequested
Var Parameters

!ifndef PAYLOAD
  !error "Run tools/windows_installer/build.py to supply the verified payload."
!endif

; Identity is supplied by the verified RELEASE.json metadata in build.py.
!ifndef APP_ID
  !error "Missing verified edition identity."
!endif
!define KEY "Software\${APP_ID}"
!define UNKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"
!define MUTEX "Local\${APP_ID}.Installed.Running"
!define START_INSTALL_MUTEX "Local\${APP_ID}.Installed.StartInstall"
; The UI lifetime guard is separate from the short app-launch/file-write gate.
; Keep it independent of release version so two upgrade wizards cannot coexist.
!define SETUP_INSTANCE_MUTEX "Local\${APP_ID}.Setup.Instance"
!define SETUP_WINDOW_PROPERTY "${APP_ID}.Setup.Window"

Name "${APP} ${APP_DISPLAY_VERSION}"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\${APP_ID}"
InstallDirRegKey HKCU "${KEY}" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 32
CRCCheck on
ManifestDPIAware true
ManifestSupportedOS all
SetFont "Segoe UI" 9
BrandingText "${APP}"
ShowInstDetails nevershow
ShowUninstDetails nevershow
!define MUI_ICON "../../static/favicon.ico"
!define MUI_UNICON "../../static/favicon.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "assets/setup-sidebar.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "assets/uninstall-sidebar.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "assets/setup-header.bmp"
!define MUI_HEADERIMAGE_RIGHT
!define MUI_BGCOLOR "FFFFFF"
!define MUI_TEXTCOLOR "14212B"
VIProductVersion "${APP_VERSION}.1"
VIAddVersionKey /LANG=1033 "ProductName" "${APP}"
VIAddVersionKey /LANG=1033 "FileDescription" "${APP} offline installer (Windows x64)"
VIAddVersionKey /LANG=1033 "FileVersion" "${APP_VERSION}.1"
VIAddVersionKey /LANG=1033 "ProductVersion" "${APP_DISPLAY_VERSION}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Third-party license notices are included."

!define MUI_ABORTWARNING
; MUI2 owns .onGUIInit/un.onGUIInit. Register hooks before MUI_LANGUAGE
; generates those callbacks rather than declaring duplicate functions.
!define MUI_CUSTOMFUNCTION_GUIINIT PublishInstallerWindow
!define MUI_CUSTOMFUNCTION_UNGUIINIT un.PublishInstallerWindow
!define MUI_WELCOMEPAGE_TITLE "${APP} ${APP_DISPLAY_VERSION}"
!define MUI_WELCOMEPAGE_TEXT "${RELEASE_NOTICE}$\r$\n$\r$\nInstall your local workspace for exposure review, attribution and notification.$\r$\n$\r$\nThen connect your APIs, choose your agency and jurisdiction, and set an optional retrieval schedule.$\r$\n$\r$\nEverything needed to run the app is included. Existing working records are kept by default."
!define MUI_FINISHPAGE_TITLE "${APP} is installed"
!define MUI_FINISHPAGE_TEXT "Open ${APP} to finish setting up your workspace.$\r$\n$\r$\nFirst-time setup guides you through API connections, your agency and jurisdiction, and optional scheduling. Existing workspaces open with their saved settings.$\r$\n$\r$\nYou can revisit these choices in Settings. Your records are stored separately from the program."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Continue to setup or open my workspace"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchWorkbench
!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipUpdatePage
!insertmacro MUI_PAGE_WELCOME
; Chaos has a fixed location so /D cannot direct it into the normal install.
!if "${APP_EDITION}" != "chaos"
  !define MUI_PAGE_CUSTOMFUNCTION_PRE SkipUpdatePage
  !insertmacro MUI_PAGE_DIRECTORY
!endif
Page custom DataChoicePage DataChoiceLeave
!insertmacro MUI_PAGE_INSTFILES
!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipUpdatePage
!insertmacro MUI_PAGE_FINISH
!define MUI_UNCONFIRMPAGE_TEXT_TOP "Remove the application and shortcuts? Your working data, original scan files, reports, and case records will remain in $LOCALAPPDATA\${APP_ID}."
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH
!insertmacro MUI_LANGUAGE "English"

!macro FocusExistingSetup
  ; .onInit precedes .onGUIInit. A simultaneous second launch may arrive before
  ; the first has published its window marker. Wait briefly, never open a second
  ; wizard or focus an unrelated NSIS dialog merely because its caption matches.
  StrCpy $2 0
  ${Do}
    StrCpy $3 0
    ${Do}
      FindWindow $3 "#32770" "" "" $3
      ${If} $3 == 0
        ${ExitDo}
      ${EndIf}
      System::Call 'user32::GetPropW(p r3, w "${SETUP_WINDOW_PROPERTY}") p.r0'
      ${If} $0 != 0
        System::Call 'user32::IsIconic(p r3) i.r0'
        ${If} $0 != 0
          System::Call 'user32::ShowWindow(p r3, i 9)' ; SW_RESTORE
        ${EndIf}
        System::Call 'user32::GetLastActivePopup(p r3) p.r4'
        ${If} $4 == 0
          StrCpy $4 $3
        ${EndIf}
        ; Windows may decline foreground activation; it must never allow a
        ; duplicate installer just because activation was not permitted.
        System::Call 'user32::SetForegroundWindow(p r4)'
        StrCpy $2 20
        ${ExitDo}
      ${EndIf}
    ${Loop}
    ${If} $2 >= 20
      ${ExitDo}
    ${EndIf}
    Sleep 100
    IntOp $2 $2 + 1
  ${LoopWhile} $2 < 20
!macroend

!macro AcquireSetupInstance
  StrCpy $SetupInstance 0
  System::Call 'kernel32::CreateMutexW(p 0, i 0, w "${SETUP_INSTANCE_MUTEX}") p.r0 ?e'
  Pop $1 ; GetLastError must be captured atomically with CreateMutexW.
  ${If} $0 == 0
    MessageBox MB_OK|MB_ICONSTOP "Setup could not verify that it is the only installer running. No program files were changed." /SD IDOK
    SetErrorLevel 6
    Abort
  ${EndIf}
  ${If} $1 == 183 ; ERROR_ALREADY_EXISTS
    System::Call 'kernel32::CloseHandle(p r0)'
    ${IfNot} ${Silent}
      !insertmacro FocusExistingSetup
    ${EndIf}
    SetErrorLevel 1618 ; Another installation is already running.
    Abort
  ${EndIf}
  ; Presence of this handle guards the entire wizard, including its Finish page.
  ; No ownership/wait is needed, and a terminated process releases it in Windows.
  StrCpy $SetupInstance $0
!macroend

!macro PublishSetupWindow
  System::Call 'user32::SetPropW(p $HWNDPARENT, w "${SETUP_WINDOW_PROPERTY}", p 1)'
!macroend

!macro ReleaseSetupInstance
  System::Call 'user32::RemovePropW(p $HWNDPARENT, w "${SETUP_WINDOW_PROPERTY}")'
  ${If} $SetupInstance != 0
    System::Call 'kernel32::CloseHandle(p $SetupInstance)'
    StrCpy $SetupInstance 0
  ${EndIf}
!macroend

!macro CheckNotRunning
  System::Call 'kernel32::OpenMutexW(i 0x100000, i 0, w "${MUTEX}") p.r0 ?e'
  Pop $1 ; Capture GetLastError inside the call before the plug-in changes it.
  ${If} $0 != 0
    System::Call 'kernel32::CloseHandle(p r0)'
    MessageBox MB_OK|MB_ICONEXCLAMATION "Close ${APP} and Demo console windows before installing or uninstalling. Your records will be preserved." /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
  ${If} $1 != 2 ; ERROR_FILE_NOT_FOUND is the only evidence of no running object.
    MessageBox MB_OK|MB_ICONSTOP "Setup could not verify whether ${APP} is running and cannot continue safely. Close its windows and retry." /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
!macroend

!macro AcquireInstallGate
  ${If} $InstallGate == 0
    System::Call 'kernel32::CreateMutexW(p 0, i 0, w "${START_INSTALL_MUTEX}") p.r0'
    StrCpy $InstallGate $0
    ${If} $InstallGate == 0
      MessageBox MB_OK|MB_ICONSTOP "Setup could not acquire the application installation guard. No program files were replaced." /SD IDOK
      SetErrorLevel 6
      Abort
    ${EndIf}
    ; Brief application registration may own the gate. Never replace files
    ; while another installer owns it, even if no backend has started yet.
    System::Call 'kernel32::WaitForSingleObject(p $InstallGate, i 5000) i.r0'
    ${If} $0 != 0
    ${AndIf} $0 != 128 ; WAIT_ABANDONED also transfers ownership.
      System::Call 'kernel32::CloseHandle(p $InstallGate)'
      StrCpy $InstallGate 0
      MessageBox MB_OK|MB_ICONEXCLAMATION "Another installation or application launch is in progress. Wait for it to finish, then retry setup." /SD IDOK
      SetErrorLevel 6
      Abort
    ${EndIf}
  ${EndIf}
!macroend

!macro ReleaseInstallGate
  ${If} $InstallGate != 0
    System::Call 'kernel32::ReleaseMutex(p $InstallGate)'
    System::Call 'kernel32::CloseHandle(p $InstallGate)'
    StrCpy $InstallGate 0
  ${EndIf}
!macroend

Function .onInit
  SetShellVarContext current
  StrCpy $InstallGate 0
  StrCpy $UpdateRequested ""
  StrCpy $RestartRequested ""
  ${GetParameters} $Parameters
  ClearErrors
  ${GetOptions} $Parameters "/UPDATE" $0
  ${IfNot} ${Errors}
    StrCpy $UpdateRequested "yes"
  ${EndIf}
  ClearErrors
  ${GetOptions} $Parameters "/RESTART" $0
  ${IfNot} ${Errors}
    StrCpy $RestartRequested "yes"
  ${EndIf}
  !insertmacro AcquireSetupInstance
  ; Unattended installs always retain data; deletion requires the interactive page.
  StrCpy $DataChoice "retain"
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "This package requires 64-bit Windows 10 or Windows 11." /SD IDOK
    SetErrorLevel 3
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_OK|MB_ICONSTOP "This package requires Windows 10 or Windows 11." /SD IDOK
    SetErrorLevel 3
    Abort
  ${EndIf}
  SetRegView 64
  ; Read again after selecting the 64-bit registry view for repeat installs.
  ReadRegStr $0 HKCU "${KEY}" "InstallLocation"
  ${If} $0 != ""
    StrCpy $INSTDIR $0
  ${EndIf}
  Call WaitForUpdateExit
  !insertmacro CheckNotRunning
FunctionEnd

Function SkipUpdatePage
  ${If} $UpdateRequested == "yes"
    Abort
  ${EndIf}
FunctionEnd

Function WaitForUpdateExit
  ${If} $UpdateRequested == "yes"
    ; The app launches verified setup first, then shuts down after its HTTP reply.
    ; Wait for that process to release its lifetime mutex before replacing files.
    StrCpy $5 0
    ${Do}
      System::Call 'kernel32::OpenMutexW(i 0x100000, i 0, w "${MUTEX}") p.r0 ?e'
      Pop $1
      ${If} $0 == 0
        ${ExitDo}
      ${EndIf}
      System::Call 'kernel32::CloseHandle(p r0)'
      Sleep 250
      IntOp $5 $5 + 1
    ${LoopWhile} $5 < 120
  ${EndIf}
FunctionEnd

Function PublishInstallerWindow
  !insertmacro PublishSetupWindow
FunctionEnd

Function DataChoicePage
  ${If} $UpdateRequested == "yes"
    Abort
  ${EndIf}
  ${IfNot} ${FileExists} "$LOCALAPPDATA\${APP_ID}\data\*.*"
    ${AndIfNot} ${FileExists} "$LOCALAPPDATA\${APP_ID}\.data-companion-transfer\*.*"
    ${AndIfNot} ${FileExists} "$LOCALAPPDATA\${APP_ID}\data-restore-points\*.*"
    Abort
  ${EndIf}
  !insertmacro MUI_HEADER_TEXT "Existing working data" "Choose whether to keep your current records."
  nsDialogs::Create 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}
  ${NSD_CreateLabel} 0 0 100% 36u "Working records were found in:$\r$\n$LOCALAPPDATA\${APP_ID}\data"
  Pop $0
  ${NSD_CreateRadioButton} 0 45u 100% 20u "Retain existing data (recommended)"
  Pop $RetainDataRadio
  ${NSD_CreateRadioButton} 0 75u 100% 20u "Delete existing data and start fresh"
  Pop $FreshDataRadio
  ${NSD_CreateLabel} 0 105u 100% 45u "Starting fresh deletes records, evidence, original files, completed reports, settings, managed restore points, and any pending import. Export your data from the app first if you need a copy."
  Pop $0
  ${If} $DataChoice == "delete"
    ${NSD_Check} $FreshDataRadio
  ${Else}
    ${NSD_Check} $RetainDataRadio
  ${EndIf}
  nsDialogs::Show
FunctionEnd

Function DataChoiceLeave
  ${NSD_GetState} $FreshDataRadio $0
  ${If} $0 == ${BST_CHECKED}
    MessageBox MB_YESNO|MB_ICONEXCLAMATION|MB_DEFBUTTON2 "Permanently delete all existing working data and start fresh?$\r$\n$\r$\nThis includes records, original files, evidence, reports, settings, managed restore points, and pending imports. This cannot be undone without an exported backup.$\r$\n$\r$\n$LOCALAPPDATA\${APP_ID}\data" /SD IDNO IDYES confirm_fresh
    Abort
    confirm_fresh:
    StrCpy $DataChoice "delete"
  ${Else}
    StrCpy $DataChoice "retain"
  ${EndIf}
FunctionEnd

Function LaunchWorkbench
  Exec '"$INSTDIR\runtime\python.exe" -I -B "$INSTDIR\app\desktop.py"'
FunctionEnd

!macro StageMaintenanceRuntime
  ; Never rely on a stale or partly uninstalled interpreter for maintenance.
  ; Only the embedded runtime's top-level standard-library/DLL files are needed.
  SetOutPath "$PLUGINSDIR\maintenance-runtime"
  File "${PAYLOAD}/runtime/*.*"
  SetOutPath "$PLUGINSDIR"
  File /oname=upgrade_cleanup.py "upgrade_cleanup.py"
  File /oname=windows_schedule.py "../../workbench/windows_schedule.py"
  File /oname=next-payload-manifest.json "${PAYLOAD}/payload-manifest.json"
!macroend

!macro CheckInstallLocation
!if "${APP_EDITION}" == "chaos"
  GetFullPathName $0 "$INSTDIR"
  GetFullPathName $1 "$LOCALAPPDATA\Programs\${APP_ID}"
  ${If} $0 != $1
    MessageBox MB_OK|MB_ICONSTOP "${APP} must use its separate installation folder:$\r$\n$1$\r$\n$\r$\nOther installations have not been changed." /SD IDOK
    SetErrorLevel 4
    Abort
  ${EndIf}
!endif
  ; Refuse linked/junction installation directories, including fresh installs.
  ; The helper checks every existing program destination during upgrades.
  StrCpy $2 $INSTDIR
  ${Do}
    System::Call 'kernel32::GetFileAttributesW(w r2) i.r3'
    ${If} $3 != -1
      IntOp $3 $3 & 0x400
      ${If} $3 != 0
        MessageBox MB_OK|MB_ICONSTOP "The installation path contains a link or junction. Select a regular installation folder." /SD IDOK
        SetErrorLevel 4
        Abort
      ${EndIf}
    ${EndIf}
    ${GetParent} "$2" $3
    ${If} $3 == $2
      ${ExitDo}
    ${EndIf}
    StrCpy $2 $3
  ${LoopUntil} $2 == ""
!macroend

Function CheckInstallPath
  !insertmacro CheckInstallLocation
FunctionEnd

Section "${APP}" SEC_MAIN
  ; Atomic with every 0.9.96+ launch registration. Keep this ownership until
  ; all program files and installer metadata have been committed.
  !insertmacro AcquireInstallGate
  !insertmacro CheckNotRunning
  Call CheckInstallPath
  ; Use a fresh helper outside the installation; never execute the old app or
  ; import its packages while deciding which old program files can be removed.
  InitPluginsDir
  !insertmacro StageMaintenanceRuntime
  File /oname=workspace_data.py "workspace_data.py"
  StrCpy $2 ""
  ${If} $DataChoice == "delete"
    StrCpy $2 "--reset-data"
  ${EndIf}
  ReadRegStr $3 HKCU "${KEY}" "InstallLocation"
  ${If} $3 != ""
    GetFullPathName $3 "$3"
    GetFullPathName $4 "$INSTDIR"
    ${If} $3 == $4
      StrCpy $2 "$2 --known-installation"
    ${EndIf}
  ${EndIf}
  DetailPrint "Checking the existing installation and preserving working records..."
    nsExec::ExecToStack '"$PLUGINSDIR\maintenance-runtime\python.exe" -I -S -B "$PLUGINSDIR\upgrade_cleanup.py" --install-dir "$INSTDIR" --next-manifest "$PLUGINSDIR\next-payload-manifest.json" $2'
    Pop $0
    Pop $1
    ${If} $0 != 0
      DetailPrint "$1"
      MessageBox MB_OK|MB_ICONSTOP "Setup could not safely repair or update the existing program files.$\r$\n$\r$\n$1$\r$\n$\r$\nYour working records are retained. Review the details and retry." /SD IDOK
      SetErrorLevel 4
      Abort
    ${EndIf}
    DetailPrint "$1"
  DetailPrint "Installing the application and its isolated runtime..."
  SetOutPath "$INSTDIR"
  SetOverwrite on
  ClearErrors
  File /r "${PAYLOAD}/*"
  ${If} ${Errors}
    MessageBox MB_OK|MB_ICONSTOP "Some program files could not be installed. Close any application windows and retry setup. Your working records are retained." /SD IDOK
    SetErrorLevel 5
    Abort
  ${EndIf}
  ${If} $DataChoice == "delete"
    !insertmacro CheckNotRunning
    nsExec::ExecToStack '"$PLUGINSDIR\maintenance-runtime\python.exe" -I -S -B "$PLUGINSDIR\workspace_data.py" --confirmation DELETE --edition ${APP_EDITION} --variant "${APP_VARIANT}"'
    Pop $0
    Pop $1
    ${If} $0 != 0
      DetailPrint "$1"
      MessageBox MB_OK|MB_ICONSTOP "Setup could not complete the requested data reset.$\r$\n$\r$\n$1" /SD IDOK
      SetErrorLevel 5
      Abort
    ${EndIf}
    DetailPrint "$1"
  ${EndIf}
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  ; Only standard releases own the legacy shortcuts.
!if "${APP_EDITION}" == "standard"
  Delete "$DESKTOP\Outreach Workbench.lnk"
  Delete "$SMPROGRAMS\Outreach Workbench\Outreach Workbench.lnk"
  Delete "$SMPROGRAMS\Outreach Workbench\Workbench Demo.lnk"
  Delete "$SMPROGRAMS\Outreach Workbench\Working data.lnk"
  Delete "$SMPROGRAMS\Outreach Workbench\Getting started.lnk"
  Delete "$SMPROGRAMS\Outreach Workbench\Uninstall.lnk"
  RMDir "$SMPROGRAMS\Outreach Workbench"
!endif
  CreateDirectory "$LOCALAPPDATA\${APP_ID}\data"
  ClearErrors
  CreateDirectory "$SMPROGRAMS\${APP}"
  CreateShortCut "$SMPROGRAMS\${APP}\${APP}.lnk" "$INSTDIR\runtime\python.exe" '-I -B "$INSTDIR\app\desktop.py"' "$INSTDIR\app\static\favicon.ico" 0 SW_SHOWNORMAL "" "Open the local notification workspace"
  CreateShortCut "$SMPROGRAMS\${APP}\${DEMO_NAME}.lnk" "$INSTDIR\runtime\python.exe" '-I -B "$INSTDIR\app\desktop.py" --demo' "$INSTDIR\app\static\favicon.ico" 0 SW_SHOWNORMAL "" "Explore separate synthetic records"
  CreateShortCut "$SMPROGRAMS\${APP}\Check installation.lnk" "$INSTDIR\runtime\python.exe" '-I -B "$INSTDIR\app\desktop.py" --self-test'
  CreateShortCut "$SMPROGRAMS\${APP}\Application logs.lnk" "$LOCALAPPDATA\${APP_ID}\data-logs"
  CreateShortCut "$SMPROGRAMS\${APP}\Working data.lnk" "$LOCALAPPDATA\${APP_ID}\data"
  CreateShortCut "$SMPROGRAMS\${APP}\Getting started.lnk" "$INSTDIR\Getting started.txt"
  CreateShortCut "$SMPROGRAMS\${APP}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortCut "$DESKTOP\${APP}.lnk" "$INSTDIR\runtime\python.exe" '-I -B "$INSTDIR\app\desktop.py"' "$INSTDIR\app\static\favicon.ico" 0 SW_SHOWNORMAL "" "Open the local notification workspace"
  ; Same installed identity, new public name. Create the replacement shortcuts
  ; first and remove only the known old DarkMatter links, never other editions
  ; or unrecognized files in the old Start menu folder.
!if "${APP_VARIANT}" == "dark_matter"
!if "${APP}" != "Shadowserver Companion DarkMatter"
  IfErrors keep_legacy_darkmatter_links
  Delete "$DESKTOP\Shadowserver Companion DarkMatter.lnk"
  Delete "$SMPROGRAMS\Shadowserver Companion DarkMatter\Shadowserver Companion DarkMatter.lnk"
  Delete "$SMPROGRAMS\Shadowserver Companion DarkMatter\Companion DarkMatter Demo.lnk"
  Delete "$SMPROGRAMS\Shadowserver Companion DarkMatter\Check installation.lnk"
  Delete "$SMPROGRAMS\Shadowserver Companion DarkMatter\Application logs.lnk"
  Delete "$SMPROGRAMS\Shadowserver Companion DarkMatter\Working data.lnk"
  Delete "$SMPROGRAMS\Shadowserver Companion DarkMatter\Getting started.lnk"
  Delete "$SMPROGRAMS\Shadowserver Companion DarkMatter\Uninstall.lnk"
  RMDir "$SMPROGRAMS\Shadowserver Companion DarkMatter"
  keep_legacy_darkmatter_links:
!endif
!endif
  WriteRegStr HKCU "${KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNKEY}" "DisplayName" "${APP}"
  WriteRegStr HKCU "${UNKEY}" "DisplayVersion" "${APP_DISPLAY_VERSION}"
  WriteRegStr HKCU "${UNKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNKEY}" "DisplayIcon" "$INSTDIR\app\static\favicon.ico,0"
  WriteRegStr HKCU "${UNKEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "${UNKEY}" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
  WriteRegDWORD HKCU "${UNKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNKEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKCU "${UNKEY}" "EstimatedSize" $0
  !insertmacro ReleaseInstallGate
SectionEnd

Function .onInstSuccess
  ${If} $UpdateRequested == "yes"
  ${AndIf} $RestartRequested == "yes"
    Call LaunchWorkbench
  ${EndIf}
FunctionEnd

Function .onInstFailed
  !insertmacro ReleaseInstallGate
FunctionEnd

Function .onGUIEnd
  !insertmacro ReleaseInstallGate
  !insertmacro ReleaseSetupInstance
FunctionEnd

Function un.onInit
  SetShellVarContext current
  StrCpy $InstallGate 0
  !insertmacro AcquireSetupInstance
  SetRegView 64
  !insertmacro CheckInstallLocation
  !insertmacro CheckNotRunning
FunctionEnd

Function un.PublishInstallerWindow
  !insertmacro PublishSetupWindow
FunctionEnd

Section "Uninstall"
  !insertmacro AcquireInstallGate
  !insertmacro CheckNotRunning
  InitPluginsDir
  !insertmacro StageMaintenanceRuntime
  DetailPrint "Removing application runtime caches; keeping working records..."
  nsExec::ExecToStack '"$PLUGINSDIR\maintenance-runtime\python.exe" -I -S -B "$PLUGINSDIR\upgrade_cleanup.py" --install-dir "$INSTDIR" --next-manifest "$PLUGINSDIR\next-payload-manifest.json" --uninstall'
  Pop $0
  Pop $1
  ${If} $0 != 0
    DetailPrint "$1"
    MessageBox MB_OK|MB_ICONSTOP "Removal could not safely inspect the program files.$\r$\n$\r$\n$1$\r$\n$\r$\nYour working records are retained." /SD IDOK
    SetErrorLevel 4
    Abort
  ${EndIf}
  ; Remove this workspace's optional task before its interpreter is removed.
  ; Other workspaces, credentials and working records remain untouched.
    nsExec::ExecToLog '"$PLUGINSDIR\maintenance-runtime\python.exe" -I -S -B "$PLUGINSDIR\upgrade_cleanup.py" --install-dir "$INSTDIR" --next-manifest "$PLUGINSDIR\next-payload-manifest.json" --remove-task'
    Pop $0
    ${If} $0 != 0
      DetailPrint "Windows could not remove the optional scheduled task."
    ${EndIf}
  ; Delete only installer-owned files. Never recursively delete a workspace.
  !include "${UNINSTALL_INVENTORY}"
  ClearErrors
  Delete "$INSTDIR\Uninstall.exe"
  ${If} ${Errors}
    MessageBox MB_OK|MB_ICONSTOP "The uninstaller could not finish removing program files. Retry uninstall after closing any application windows. Working records are retained." /SD IDOK
    SetErrorLevel 5
    Abort
  ${EndIf}
  RMDir "$INSTDIR"
  Delete "$DESKTOP\${APP}.lnk"
  Delete "$SMPROGRAMS\${APP}\${APP}.lnk"
  Delete "$SMPROGRAMS\${APP}\${DEMO_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP}\Check installation.lnk"
  Delete "$SMPROGRAMS\${APP}\Application logs.lnk"
  Delete "$SMPROGRAMS\${APP}\Working data.lnk"
  Delete "$SMPROGRAMS\${APP}\Getting started.lnk"
  Delete "$SMPROGRAMS\${APP}\Uninstall.lnk"
  RMDir "$SMPROGRAMS\${APP}"
  DeleteRegKey HKCU "${UNKEY}"
  DeleteRegKey HKCU "${KEY}"
  !insertmacro ReleaseInstallGate
SectionEnd

Function un.onUninstFailed
  !insertmacro ReleaseInstallGate
FunctionEnd

Function un.onGUIEnd
  !insertmacro ReleaseInstallGate
  !insertmacro ReleaseSetupInstance
FunctionEnd
