@echo off
rem Usage: restore_database.bat dump_file [/verify]
rem   dump_file: a bare file name is looked up in D:\medicina-naturista-backups; with a path it is used as given.
rem   /verify restores into a throwaway database and drops it; the real one is untouched.
rem   Without it the real database is replaced: the application container is stopped first and
rem   started again after a successful restore (left stopped if the restore fails).
rem Progress goes to the console and to restore.log next to the dump file (appended on every run).
rem pg_restore runs with --verbose; its per-object output is written to the log only.
setlocal
set "CONTAINER=medicina-db"
set "APP_CONTAINER=medicina"
set "DB_USER=medicina"
set "DB=medicina"
set "REMOTE=/tmp/restore.dump"
set "BACKUP_DIR=D:\medicina-naturista-backups"

if "%~1"=="" (
    echo Usage: %~nx0 dump_file [/verify]
    exit /b 1
)
set "DUMP=%~f1"
if "%~1"=="%~nx1" set "DUMP=%BACKUP_DIR%\%~1"
if not exist "%DUMP%" (
    echo Dump not found: %DUMP%
    exit /b 1
)
for %%i in ("%DUMP%") do set "LOG=%%~dpirestore.log"
set "TARGET=%DB%"
set "VERIFY="
if /i "%~2"=="/verify" set "VERIFY=1"
if defined VERIFY set "TARGET=%DB%_verify"

if defined VERIFY (
    call :log "Restore started: verify mode, %DUMP% into temporary database %TARGET%"
    goto :run
)
call :log "Restore started: %DUMP% into database %TARGET% in container %CONTAINER%"
echo This replaces the contents of database %DB% in %CONTAINER% with %DUMP%.
set /p "ANSWER=Type YES to continue: "
if /i not "%ANSWER%"=="YES" (
    call :log "Cancelled by the user, nothing was changed"
    exit /b 1
)

:run
rem The app keeps pooled connections that break when the restore recreates the pgvector type.
if defined VERIFY goto :copy
set "APP_RUNNING="
set "APP_STOPPED="
for /f %%s in ('docker inspect -f "{{.State.Running}}" %APP_CONTAINER% 2^>nul') do if "%%s"=="true" set "APP_RUNNING=1"
if not defined APP_RUNNING goto :copy
call :log "Stopping the application container %APP_CONTAINER%"
>>"%LOG%" docker stop %APP_CONTAINER% 2>&1 || goto :fail
set "APP_STOPPED=1"

:copy
call :log "Step 1/3: copying the dump into the container (%REMOTE%)"
>>"%LOG%" docker cp "%DUMP%" %CONTAINER%:%REMOTE% 2>&1 || goto :fail

if defined VERIFY goto :verify_run
set "EXISTS="
for /f "usebackq" %%n in (`docker exec %CONTAINER% psql -U %DB_USER% -d postgres -t -A -c "SELECT 1 FROM pg_database WHERE datname='%TARGET%';"`) do set "EXISTS=%%n"
if defined EXISTS goto :restore_real
call :log "Database %TARGET% does not exist, creating it"
>>"%LOG%" docker exec %CONTAINER% createdb -U %DB_USER% %TARGET% 2>&1 || goto :fail

:restore_real
call :log "Step 2/3: restoring into %TARGET% with --clean --if-exists"
>>"%LOG%" docker exec %CONTAINER% pg_restore -U %DB_USER% -d %TARGET% --clean --if-exists -v %REMOTE% 2>&1 || goto :fail
call :log "Step 3/3: cleaning up"
goto :done

:verify_run
call :log "Step 2/3: creating %TARGET% and restoring into it"
>>"%LOG%" docker exec %CONTAINER% createdb -U %DB_USER% %TARGET% 2>&1 || goto :fail
>>"%LOG%" docker exec %CONTAINER% pg_restore -U %DB_USER% -d %TARGET% --no-owner -v %REMOTE% 2>&1 || goto :fail
call :log "Step 3/3: counting tables in %TARGET%"
set "TABLES="
for /f "usebackq" %%n in (`docker exec %CONTAINER% psql -U %DB_USER% -d %TARGET% -t -A -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"`) do set "TABLES=%%n"
if not defined TABLES goto :fail
call :log "Verified: %TARGET% has %TABLES% tables"

:done
call :cleanup
if defined APP_STOPPED (
    call :log "Starting the application container %APP_CONTAINER%"
    >>"%LOG%" docker start %APP_CONTAINER% 2>&1 || goto :fail
)
call :log "Restore into %TARGET% finished"
exit /b 0

:fail
set "RC=%errorlevel%"
if "%RC%"=="0" set "RC=1"
call :cleanup
call :log "FAILED with exit code %RC%; see the lines above in %LOG%"
if defined APP_STOPPED call :log "The application container %APP_CONTAINER% was left stopped; start it with: docker start %APP_CONTAINER%"
exit /b 1

:cleanup
if defined VERIFY (
    call :log "Dropping temporary database %TARGET%"
    docker exec %CONTAINER% dropdb -U %DB_USER% --if-exists %TARGET% >nul 2>>"%LOG%"
)
docker exec %CONTAINER% rm -f %REMOTE% >nul 2>&1
exit /b 0

:log
echo [%date% %time:~0,8%] %~1
>>"%LOG%" echo [%date% %time:~0,8%] %~1
exit /b 0
