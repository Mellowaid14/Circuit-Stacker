@echo off
set "PROJECT_ROOT=%~dp0"
if exist "%PROJECT_ROOT%.venv\Scripts\pythonw.exe" (
    start "" "%PROJECT_ROOT%.venv\Scripts\pythonw.exe" "%PROJECT_ROOT%launch_ams2_show_livery_ids.py"
) else (
    start "" py "%PROJECT_ROOT%launch_ams2_show_livery_ids.py"
)
