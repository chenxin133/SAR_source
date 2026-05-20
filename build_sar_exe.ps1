$ErrorActionPreference = "Stop"

$root = "E:\SAR"
$front = Join-Path $root "SAR_Front"
$backend = Join-Path $root "SAR_Backend"
$out = Join-Path $root "SAR_exe"
$work = Join-Path $root ".build\pyinstaller"

Write-Host "1) 构建前端 dist..."
Push-Location $front
npm ci
npm run build
Pop-Location

Write-Host "2) 安装打包工具..."
py -m pip install --upgrade pip
py -m pip install pyinstaller

Write-Host "3) 清理输出目录..."
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Path $out | Out-Null

Write-Host "4) 打包后端为 Windows 可执行..."
Push-Location $backend
py -m PyInstaller `
  --noconfirm `
  --clean `
  --onedir `
  --name "SAR_App" `
  --distpath $out `
  --workpath $work `
  --specpath $work `
  --paths $backend `
  --hidden-import "app.main" `
  --collect-submodules "app" `
  run_standalone.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败" }
Pop-Location

Write-Host "5) 复制前端静态资源..."
$frontendOut = Join-Path $out "SAR_App\frontend"
New-Item -ItemType Directory -Force -Path $frontendOut | Out-Null
Copy-Item -Recurse -Force (Join-Path $front "dist\*") $frontendOut

Write-Host "5.1) 复制后端 app 源码（保障可执行版可加载 app 包）..."
$appOut = Join-Path $out "SAR_App\app"
if (Test-Path $appOut) { Remove-Item -Recurse -Force $appOut }
Copy-Item -Recurse -Force (Join-Path $backend "app") $appOut

Write-Host "6) 生成一键启动脚本..."
$startBat = @"
@echo off
setlocal
cd /d %~dp0SAR_App
set "PYTHONPATH=%CD%"
start "" "%~dp0SAR_App\SAR_App.exe"
timeout /t 2 >nul
start "" http://127.0.0.1:8000
echo SAR 应用已启动，浏览器地址: http://127.0.0.1:8000
pause
"@
Set-Content -Path (Join-Path $out "Start_SAR.bat") -Value $startBat -Encoding ASCII

$debugBat = @"
@echo off
setlocal
set "ROOT=%~dp0"
set "APPDIR=%ROOT%SAR_App"
set "LOGDIR=%ROOT%logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "LOGFILE=%LOGDIR%\sar_app_start.log"

echo ==== %date% %time% ==== > "%LOGFILE%"
echo App dir: %APPDIR% >> "%LOGFILE%"
echo Starting SAR_App.exe ... >> "%LOGFILE%"

cd /d "%APPDIR%"
set "PYTHONPATH=%APPDIR%"
"%APPDIR%\SAR_App.exe" >> "%LOGFILE%" 2>&1
set "EXITCODE=%ERRORLEVEL%"

echo. >> "%LOGFILE%"
echo Exit code: %EXITCODE% >> "%LOGFILE%"
echo Log file: %LOGFILE% >> "%LOGFILE%"

echo.
echo Startup finished. Exit code: %EXITCODE%
echo Log file: %LOGFILE%
if not "%EXITCODE%"=="0" (
  echo Startup failed. Please send the log file to support.
  type "%LOGFILE%"
)
pause
"@
Set-Content -Path (Join-Path $out "Start_SAR_Debug.bat") -Value $debugBat -Encoding ASCII

$readme = @"
SAR 可执行版说明

1. 双击 Start_SAR.bat 启动应用。
2. 若启动失败，双击 Start_SAR_Debug.bat，查看 logs\sar_app_start.log。
3. 首次启动会在 SAR_App\data 下自动创建 SQLite 数据库和本地对象存储。
4. 浏览器访问: http://127.0.0.1:8000

说明:
- 该版本无需 Vue 开发环境、无需 Docker。
- 数据默认保存在 SAR_App\data 目录，直接拷贝整个 SAR_exe 文件夹即可迁移。
"@
Set-Content -Path (Join-Path $out "README.txt") -Value $readme -Encoding UTF8

Write-Host "完成：$out"
