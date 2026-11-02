@echo off
rem Usage: backup_database.bat [output_dir]
rem Progress goes to the console and to backup.log in the output directory (appended on every run).
rem pg_dump runs with --verbose; its per-table output is written to the log only.
setlocal
set "CONTAINER=medicina-db"
set "DB_USER=medicina"
set "DB=medicina"
set "OUT=D:\medicina-naturista-backups"
if not "%~1"=="" set "OUT=%~1"
if not exist "%OUT%" mkdir "%OUT%"
for %%i in ("%OUT%") do set "OUT=%%~fi"
set "LOG=%OUT%\backup.log"

call :log "Backup started: container %CONTAINER%, database %DB%, output %OUT%"

rem The timestamp comes from the container, so it does not depend on the Windows locale.
set "STAMP="
for /f %%i in ('docker exec %CONTAINER% date +%%Y%%m%%d_%%H%%M%%S') do set "STAMP=%%i"
if not defined STAMP (
    call :log "FAILED: cannot reach container %CONTAINER%. Is Docker running?"
    exit /b 1
)
set "REMOTE=/tmp/%DB%_%STAMP%.dump"
set "FILE=%OUT%\%DB%_%STAMP%.dump"

call :log "Step 1/3: pg_dump into the container (%REMOTE%)"
>>"%LOG%" docker exec %CONTAINER% pg_dump -U %DB_USER% -d %DB% -Fc -v -f %REMOTE% 2>&1 || goto :fail

call :log "Step 2/3: verifying the dump table of contents"
docker exec %CONTAINER% pg_restore --list %REMOTE% >nul 2>>"%LOG%" || goto :fail

call :log "Step 3/3: copying the dump to %FILE%"
>>"%LOG%" docker cp %CONTAINER%:%REMOTE% "%FILE%" 2>&1 || goto :fail

docker exec %CONTAINER% rm -f %REMOTE%
for %%f in ("%FILE%") do set "SIZE=%%~zf"
call :log "Backup finished: %FILE% (%SIZE% bytes)"

rem Keep only the newest backups; the names sort by timestamp. Runs only after a successful backup.
set "KEEP=2"
for /f "skip=%KEEP% delims=" %%f in ('dir /b /o-n "%OUT%\%DB%_*.dump" 2^>nul') do (
    del "%OUT%\%%f" && call :log "Removed old backup: %%f"
)
exit /b 0

:fail
set "RC=%errorlevel%"
docker exec %CONTAINER% rm -f %REMOTE% >nul 2>&1
call :log "FAILED with exit code %RC%; see the lines above in %LOG%"
exit /b 1

:log
echo [%date% %time:~0,8%] %~1
>>"%LOG%" echo [%date% %time:~0,8%] %~1
exit /b 0
