; Fyodor for Windows: the installer (NSIS 3, Modern UI 2). Built by scripts/build-windows-installer.sh from dist\Fyodor
; (PyInstaller's one-folder app) on Linux with makensis, or on Windows with NSIS.
;   makensis -DVERSION=0.1.0 -DSRC=<dist/Fyodor> -DOUT=<Fyodor-Setup-0.1.0.exe> packaging/windows/fyodor.nsi
; Installs for all users into Program Files; your decks, saves and card data live in your profile (%USERPROFILE%\Fyodor)
; and stay when Fyodor is uninstalled.

; a 64-bit installer, like the app it installs (it also runs where only 64-bit Windows programs can)
Target amd64-unicode
SetCompressor /SOLID lzma

!ifndef VERSION
  !define VERSION "0.1.0"
!endif
!ifndef SRC
  !define SRC "..\..\dist\Fyodor"
!endif
!ifndef OUT
  !define OUT "..\..\Fyodor-Setup-${VERSION}.exe"
!endif

!define APP "Fyodor"
!define EXE "Fyodor.exe"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP}"
!define FIREWALL_RULE "Fyodor (LAN Night)"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"

Name "${APP}"
OutFile "${OUT}"
InstallDir "$PROGRAMFILES64\${APP}"
InstallDirRegKey HKLM "${UNINST_KEY}" "InstallLocation"
RequestExecutionLevel admin
ManifestDPIAware true
BrandingText "${APP} ${VERSION}"

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APP}"
VIAddVersionKey "FileDescription" "${APP} installer: Commander game nights on your own network"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "Fyodor contributors"

!define MUI_ICON "fyodor.ico"
!define MUI_UNICON "fyodor.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Fyodor ${VERSION}"
!define MUI_WELCOMEPAGE_TEXT "Fyodor runs Commander game nights on your own network: one computer hosts, everyone else joins from a browser or their own Fyodor.$\r$\n$\r$\nThe first start downloads the card database from Scryfall. After that, Fyodor works offline.$\r$\n$\r$\nClick Next to continue."
!define MUI_COMPONENTSPAGE_SMALLDESC
!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Start Fyodor now"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "Fyodor needs 64-bit Windows."
    Abort
  ${EndIf}
  SetRegView 64
  SetShellVarContext all ; installed for everyone: the shortcuts go in the shared Start menu and desktop
FunctionEnd

Function un.onInit
  SetRegView 64
  SetShellVarContext all
FunctionEnd

Section "Fyodor (required)" SecApp
  SectionIn RO
  ; a running Fyodor would hold its files open
  nsExec::Exec 'taskkill /IM "${EXE}" /F'
  Pop $0
  SetOutPath "$INSTDIR"
  ; replace an older install's program files (never the user's data, which isn't here)
  RMDir /r "$INSTDIR\_internal"
  File /r "${SRC}\*"
  File "/oname=$INSTDIR\fyodor.ico" "fyodor.ico"
  WriteUninstaller "$INSTDIR\Uninstall Fyodor.exe"

  CreateShortcut "$SMPROGRAMS\${APP}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\fyodor.ico" 0

  WriteRegStr HKLM "${UNINST_KEY}" "DisplayName" "${APP}"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "${UNINST_KEY}" "Publisher" "Fyodor contributors"
  WriteRegStr HKLM "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\fyodor.ico"
  WriteRegStr HKLM "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall Fyodor.exe"'
  WriteRegStr HKLM "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall Fyodor.exe" /S'
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKLM "${UNINST_KEY}" "EstimatedSize" "$0"
SectionEnd

Section "Desktop shortcut" SecDesktop
  CreateShortcut "$DESKTOP\${APP}.lnk" "$INSTDIR\${EXE}" "" "$INSTDIR\fyodor.ico" 0
SectionEnd

Section "Let the pod join (Windows Firewall, private networks only)" SecFirewall
  ; LAN Night: other players' devices connect to this one (the web page on TCP, table discovery on UDP 47474).
  ; Private (home) networks only, never public Wi-Fi. Without this, Windows asks the first time Fyodor hosts.
  nsExec::Exec 'netsh advfirewall firewall delete rule name="${FIREWALL_RULE}"'
  Pop $0
  nsExec::Exec 'netsh advfirewall firewall add rule name="${FIREWALL_RULE}" dir=in action=allow program="$INSTDIR\${EXE}" enable=yes profile=private'
  Pop $0
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecApp} "Fyodor itself."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "A Fyodor shortcut on the desktop."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecFirewall} "Lets the other players' devices on your home network join your LAN Night. Private networks only."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
  nsExec::Exec 'taskkill /IM "${EXE}" /F'
  Pop $0
  nsExec::Exec 'netsh advfirewall firewall delete rule name="${FIREWALL_RULE}"'
  Pop $0
  Delete "$SMPROGRAMS\${APP}.lnk"
  Delete "$DESKTOP\${APP}.lnk"
  ; only what the installer put here: never a recursive delete of the install folder itself
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\${EXE}"
  Delete "$INSTDIR\fyodor.ico"
  Delete "$INSTDIR\Uninstall Fyodor.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKLM "${UNINST_KEY}"
SectionEnd
