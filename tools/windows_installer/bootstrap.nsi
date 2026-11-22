; Immutable installed launcher. No Python or application files load before the gate.
Unicode true
!include "LogicLib.nsh"
!include "FileFunc.nsh"

!ifndef APP_ID
  !error "APP_ID must come from verified release identity."
!endif
!ifndef OUTPUT
  !error "OUTPUT must name a fresh bootstrap build artifact."
!endif

Name "${APP_ID} launcher"
OutFile "${OUTPUT}"
RequestExecutionLevel user
ManifestSupportedOS all
CRCCheck on
SetCompressor /SOLID lzma
!define START_GATE "Local\${APP_ID}.Installed.StartInstall"
!define RUNNING "Local\${APP_ID}.Installed.Running"

Var Root
Var Arguments
Var Scheduled
Var Gate
Var Owned
Var Running
Var Attributes
Var HandleList
Var Security
Var Startup
Var ProcessInfo
Var Child
Var ChildThread
Var Python
Var Script
Var Command
Var Result
Var Failure

Function .onInit
  StrCpy $Gate 0
  StrCpy $Owned 0
  StrCpy $Running 0
  StrCpy $Attributes 0
  StrCpy $HandleList 0
  StrCpy $Security 0
  StrCpy $Startup 0
  StrCpy $ProcessInfo 0
  StrCpy $Child 0
  StrCpy $ChildThread 0
  StrCpy $Scheduled 0
  StrCpy $Result 6
  StrCpy $Failure "The application could not start safely. Retry, or repair the installation."
  ${GetParent} "$EXEDIR" $Root
  ${GetParameters} $Arguments
  StrCpy $0 $Arguments 11
  ${If} $0 == "--scheduled"
    StrCpy $0 $Arguments 1 11
    ${If} $0 == " "
    ${OrIf} $0 == ""
      StrCpy $Scheduled 1
      StrCpy $Arguments $Arguments "" 12
    ${EndIf}
  ${EndIf}
  ; GetParameters uses NSIS strings. Refuse a long command instead of truncating it.
  System::Call 'kernel32::GetCommandLineW() p.r0'
  System::Call 'kernel32::lstrlenW(p r0) i.r1'
  ${If} $1 >= ${NSIS_MAX_STRLEN}
    StrCpy $Failure "The application launch arguments are too long. Use a shorter workspace path."
    Goto done
  ${EndIf}


  System::Call 'kernel32::CreateMutexW(p 0, i 0, w "${START_GATE}") p.r0'
  StrCpy $Gate $0
  ${If} $Gate == 0
    Goto done
  ${EndIf}
  System::Call 'kernel32::WaitForSingleObject(p $Gate, i 5000) i.r0'
  ${If} $0 != 0
  ${AndIf} $0 != 128
    ${If} $0 == 258
      ; An ordinary launch can already have this image mapped while uninstall
      ; owns the gate. A persistent dialog would keep the executable locked.
      ; This expected busy transition exits promptly; repair errors still show.
      StrCpy $Failure ""
    ${EndIf}
    Goto done
  ${EndIf}
  StrCpy $Owned 1
  ReadINIStr $0 "$Root\installation-ready.ini" "installation" "app_id"
  ReadINIStr $1 "$Root\installation-ready.ini" "installation" "protocol"
  ${If} $0 != "${APP_ID}"
  ${OrIf} $1 != "1"
    StrCpy $Failure "This installation is incomplete or needs a newer launcher. Run setup again to repair it. Working records are retained."
    Goto done
  ${EndIf}
  StrCpy $Python "$Root\runtime\python.exe"
  StrCpy $Script "$Root\app\desktop.py"
  StrCpy $2 0x00080000 ; EXTENDED_STARTUPINFO_PRESENT
  ${If} $Scheduled == 1
    StrCpy $Python "$Root\runtime\pythonw.exe"
    StrCpy $Script "$Root\app\modules\accretion\tools\run_scheduled.py"
    IntOp $2 $2 | 0x08000000 ; CREATE_NO_WINDOW
  ${EndIf}
  StrLen $0 $Python
  StrLen $1 $Script
  IntOp $0 $0 + $1
  StrLen $1 $Arguments
  IntOp $0 $0 + $1
  IntOp $0 $0 + 32
  ${If} $0 >= ${NSIS_MAX_STRLEN}
    StrCpy $Failure "The application launch arguments are too long. Use a shorter workspace path."
    Goto done
  ${EndIf}
  StrCpy $Command '$\"$Python$\" -I -B $\"$Script$\" $Arguments'
  ; One inherited presence handle exists from process creation, before DLL/import
  ; loading. It survives this launcher's death until the Python child exits.
  System::Call '*(&l4, p 0, i 1) p.r0'
  StrCpy $Security $0
  ${If} $Security == 0
    Goto done
  ${EndIf}
  System::Call 'kernel32::CreateMutexW(p $Security, i 0, w "${RUNNING}") p.r0'
  StrCpy $Running $0
  ${If} $Running == 0
    Goto done
  ${EndIf}
  System::Call 'kernel32::InitializeProcThreadAttributeList(p 0, i 1, i 0, *p 0 r0)'
  ${If} $0 == 0
    Goto done
  ${EndIf}
  System::Alloc $0
  Pop $Attributes
  System::Call 'kernel32::InitializeProcThreadAttributeList(p $Attributes, i 1, i 0, *p r0) i.r1'
  ${If} $1 == 0
    System::Free $Attributes
    StrCpy $Attributes 0
    Goto done
  ${EndIf}
  System::Call '*(p $Running) p.r0'
  StrCpy $HandleList $0
  ${If} $HandleList == 0
    Goto done
  ${EndIf}
  System::Call '*0(&l.r1, p)' ; sizeof(HANDLE), matching this NSIS process
  System::Call 'kernel32::UpdateProcThreadAttribute(p $Attributes, i 0, p 0x00020002, p $HandleList, p r1, p 0, p 0) i.r0'
  ${If} $0 == 0
    Goto done
  ${EndIf}
  ; STARTUPINFOEXW, including cb computed for the NSIS pointer width.
  System::Call '*(&l4, p 0, p 0, p 0, i 0, i 0, i 0, i 0, i 0, i 0, i 0, i 0, h 0, h 0, p 0, p 0, p 0, p 0, p $Attributes) p.r0'
  StrCpy $Startup $0
  ${If} $Startup == 0
    Goto done
  ${EndIf}
  System::Call '*(p 0, p 0, i 0, i 0) p.r0'
  StrCpy $ProcessInfo $0
  ${If} $ProcessInfo == 0
    Goto done
  ${EndIf}
  ; Pass strings by register: embedded quotes/spaces must not be reparsed as
  ; System plug-in call syntax after named-variable expansion.
  StrCpy $3 $Python
  StrCpy $4 $Command
  StrCpy $5 $Root
  System::Call 'kernel32::CreateProcessW(w r3, w r4, p 0, p 0, i 1, i r2, p 0, w r5, p $Startup, p $ProcessInfo) i.r0'
  ${If} $0 == 0
    StrCpy $Failure "The installed runtime could not start. Run setup again to repair it. Working records are retained."
    Goto done
  ${EndIf}
  System::Call '*$ProcessInfo(p .r0, p .r1)'
  StrCpy $Child $0
  StrCpy $ChildThread $1
  System::Call 'kernel32::ReleaseMutex(p $Gate)'
  StrCpy $Owned 0
  System::Call 'kernel32::CloseHandle(p $Gate)'
  StrCpy $Gate 0
  System::Call 'kernel32::WaitForSingleObject(p $Child, i -1) i.r0'
  ${If} $0 == 0
    System::Call 'kernel32::GetExitCodeProcess(p $Child, *i .r0) i.r1'
    ${If} $1 != 0
      StrCpy $Result $0
      StrCpy $Failure ""
    ${EndIf}
  ${EndIf}

  done:
  ${If} $ChildThread != 0
    System::Call 'kernel32::CloseHandle(p $ChildThread)'
  ${EndIf}
  ${If} $Child != 0
    System::Call 'kernel32::CloseHandle(p $Child)'
  ${EndIf}
  ${If} $Attributes != 0
    System::Call 'kernel32::DeleteProcThreadAttributeList(p $Attributes)'
    System::Free $Attributes
  ${EndIf}
  System::Free $HandleList
  System::Free $Startup
  System::Free $ProcessInfo
  System::Free $Security
  ${If} $Running != 0
    System::Call 'kernel32::CloseHandle(p $Running)'
  ${EndIf}
  ${If} $Owned != 0
    System::Call 'kernel32::ReleaseMutex(p $Gate)'
  ${EndIf}
  ${If} $Gate != 0
    System::Call 'kernel32::CloseHandle(p $Gate)'
  ${EndIf}
  ${If} $Failure != ""
  ${AndIf} $Scheduled == 0
    MessageBox MB_OK|MB_ICONSTOP "$Failure" /SD IDOK
  ${EndIf}
  SetErrorLevel $Result
  Quit
FunctionEnd

Section
SectionEnd
