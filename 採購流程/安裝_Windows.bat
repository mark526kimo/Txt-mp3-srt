@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
echo ==== 採購流程 桌電版安裝 ====
set PY=
where py >nul 2>nul && set PY=py -3
if "%PY%"=="" ( where python >nul 2>nul && set PY=python )
if "%PY%"=="" (
  echo [錯誤] 找不到 Python。請到 https://www.python.org/downloads/ 安裝，安裝時勾選 Add python.exe to PATH，然後重新執行本檔。
  pause & exit /b 1
)
echo 使用 Python：%PY%
%PY% -m pip install --upgrade python-docx
if not exist "採購流程\cases" mkdir "採購流程\cases"
if not exist "採購流程\reference\舊檔" mkdir "採購流程\reference\舊檔"
if not exist "採購流程\reference\法規" mkdir "採購流程\reference\法規"
where claude >nul 2>nul || (
  echo.
  echo [提醒] 找不到 Claude Code。請先安裝：https://docs.claude.com/en/docs/claude-code/setup
)
echo.
echo 安裝完成。下一步：
echo  1. 把舊檔放進 採購流程\reference\舊檔\
echo  2. 把法規放進 採購流程\reference\法規\
echo  3. 雙擊「開始採購流程.bat」，輸入 /bid-run 案號
pause
