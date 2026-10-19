@echo off
setlocal
if not defined QT_ROOT (echo Set QT_ROOT to Qt 6.8.3 msvc2022_64. & exit /b 2)
if not defined OPENRGB_SOURCE (echo Set OPENRGB_SOURCE to the pinned OpenRGB checkout. & exit /b 2)
where cl >nul 2>nul
if errorlevel 1 (
  for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do call "%%i\VC\Auxiliary\Build\vcvars64.bat" >nul
)
where cl >nul 2>nul
if errorlevel 1 exit /b 2
pushd "%~dp0.."
set "PLUGIN_REPO=%CD%"
for %%P in (ram pebble-pro) do (
  if not exist "build\%%P" mkdir "build\%%P"
)
cd /d "%PLUGIN_REPO%\build\ram"
"%QT_ROOT%\bin\qmake.exe" "%PLUGIN_REPO%\plugins\ram\VColorRamPlugin.pro" -o Makefile
if errorlevel 1 exit /b 1
nmake /nologo /f Makefile
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHsc /MD /W4 "%PLUGIN_REPO%\plugins\ram\test_protocol.cpp" /Fe:test_protocol.exe /Fo:test_protocol.obj
if errorlevel 1 exit /b 1
test_protocol.exe
if errorlevel 1 exit /b 1
cd /d "%PLUGIN_REPO%\build\pebble-pro"
"%QT_ROOT%\bin\qmake.exe" "%PLUGIN_REPO%\plugins\pebble-pro\PebbleProPlugin.pro" -o Makefile
if errorlevel 1 exit /b 1
nmake /nologo /f Makefile
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHsc /MD /W4 "%PLUGIN_REPO%\plugins\pebble-pro\test_protocol.cpp" /Fe:test_protocol.exe /Fo:test_protocol.obj
if errorlevel 1 exit /b 1
test_protocol.exe
if errorlevel 1 exit /b 1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PLUGIN_REPO%\plugins\package.ps1"
if errorlevel 1 exit /b 1
popd
