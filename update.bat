@echo off
echo === CV Website Updater ===
echo.

cd /d "%~dp0"

echo [1/3] Parsing CV...
python scripts\parse_cv.py cv\YANG_CV_git.docx
if errorlevel 1 (
    echo ERROR: CV parsing failed. Make sure python-docx is installed.
    echo Run: pip install python-docx
    pause
    exit /b 1
)

echo.
echo [2/3] Committing changes...
git add -A
git commit -m "Update CV data"

echo.
echo [3/3] Pushing to GitHub...
git push

echo.
echo === Done! Website will update in ~1 minute ===
pause
