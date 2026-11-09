@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Double-click to run the importer; it asks for the preset folder.
pushd "%~dp0"
if not exist import_presets.py (
    echo Unzip the whole download first: right-click the ZIP and choose Extract All.
    echo Then run this again from the extracted folder.
    goto end
)
rem py is python.org's launcher. Its first run may download Python, so its output stays visible.
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (call python -c "" >nul 2>&1 && set "PY=python")
if not defined PY (
    echo Python isn't installed. Get it from python.org/downloads, then run this again.
    goto end
)
rem call, because python or py can itself be a .bat file (pyenv-win), which otherwise never returns here.
call %PY% import_presets.py
rem 103-112 come from an old py launcher that found no Python; import_presets.py only exits with 0-2.
if not errorlevel 103 goto end
if errorlevel 113 goto end
rem A python that works without the launcher (conda, pyenv-win, a zip install) will do instead.
call python -c "" >nul 2>&1
if not errorlevel 1 (
    echo.
    echo The Python Launcher found no Python, so this uses the python on your PATH instead.
    echo.
    call python import_presets.py
    goto end
)
echo.
echo This PC has an old Python Launcher but no Python it can use.
echo Install Python from python.org/downloads. If you already did, uninstall
echo "Python Launcher" from Settings, Apps, Installed apps, then run this again.
:end
pause
popd
exit /b 0
