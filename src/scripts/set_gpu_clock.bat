@echo off
setlocal EnableExtensions EnableDelayedExpansion
title NVIDIA GPU Clock

fltmc >nul 2>&1
if errorlevel 1 (
    schtasks.exe /run /tn "MedicinaNaturista-GpuClock" >nul 2>&1
    if not errorlevel 1 exit /b 0
    echo First run setup_gpu_clock.bat as administrator to enable launching without UAC prompts.
    echo Press any key to exit.
    pause >nul
    exit /b 1
)

where nvidia-smi.exe >nul 2>&1
if errorlevel 1 (
    echo nvidia-smi.exe was not found in PATH. Check your NVIDIA driver installation.
    echo Press any key to exit.
    pause >nul
    exit /b 1
)

set "GPU_CONFIGURED_LIMIT=unavailable (not exposed by this NVIDIA driver)"

:menu
echo(
nvidia-smi.exe -i 0 --query-gpu=name --format=csv,noheader
if errorlevel 1 echo Unable to read the GPU model.
echo Current configured frequency limit: !GPU_CONFIGURED_LIMIT!
for /f "delims=" %%A in ('nvidia-smi.exe -i 0 "--query-gpu=clocks.sm" "--format=csv,noheader"') do echo Current frequency: %%A
echo Enter the upper clock limit between 1072 and 2145 MHz.
echo The lower limit remains 210 MHz.
echo D = restore defaults ^| Q = quit
set "GPU_CLOCK_CHOICE="
set /p "GPU_CLOCK_CHOICE=Clock (MHz) / D / Q: "
if /i "!GPU_CLOCK_CHOICE!"=="Q" exit /b 0
if /i "!GPU_CLOCK_CHOICE!"=="D" goto reset

rem Validate through SET output so input is never interpreted as a command.
if not defined GPU_CLOCK_CHOICE goto invalid
rem SET treats spaces before a pipe as part of the variable prefix.
set GPU_CLOCK_CHOICE|findstr /r /x "GPU_CLOCK_CHOICE=[1-2][0-9][0-9][0-9]" >nul
if errorlevel 1 goto invalid
if !GPU_CLOCK_CHOICE! LSS 1072 goto invalid
if !GPU_CLOCK_CHOICE! GTR 2145 goto invalid

echo Running: nvidia-smi -i 0 -lgc 210,!GPU_CLOCK_CHOICE!
nvidia-smi.exe -i 0 -lgc 210,!GPU_CLOCK_CHOICE!
if errorlevel 1 goto failed
set "GPU_CONFIGURED_LIMIT=210-!GPU_CLOCK_CHOICE! MHz"
goto monitor

:reset
echo Running: nvidia-smi -i 0 -rgc
nvidia-smi.exe -i 0 -rgc
if errorlevel 1 goto failed
set "GPU_CONFIGURED_LIMIT=default (automatic boost)"
goto monitor

:invalid
echo Invalid input. Enter an integer between 1072 and 2145, D or Q.
goto menu

:failed
echo The NVIDIA command failed. Check the message above.
goto menu

:monitor
echo Current configured frequency limit: !GPU_CONFIGURED_LIMIT!
echo Monitoring GPU every 2 seconds. Press Ctrl+C to stop.

:monitor_loop
set "GPU_SAMPLE_RECEIVED="
rem Framebuffer usage measures dedicated VRAM capacity, not memory activity or shared RAM.
for /f "tokens=1-3 delims=, " %%A in ('nvidia-smi.exe -i 0 "--query-gpu=clocks.sm,temperature.gpu,memory.used" "--format=csv,noheader,nounits"') do (
    set "GPU_MEMORY_INVALID="
    for /f "delims=0123456789" %%E in ("%%C") do set "GPU_MEMORY_INVALID=1"
    if not defined GPU_MEMORY_INVALID (
        echo Frequency: %%A MHz, Temperature: %%B, Dedicated memory usage: %%C MiB
        set "GPU_SAMPLE_RECEIVED=1"
    )
)
if not defined GPU_SAMPLE_RECEIVED (
    echo Unable to read dedicated GPU memory usage.
    goto menu
)
timeout /t 2 /nobreak >nul
goto monitor_loop
