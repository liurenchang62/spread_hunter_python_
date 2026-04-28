@echo off
rem SSH into VPS using SERVER_PASSWORD via PuTTY plink (see server\login.ps1).
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0login.ps1" %*
