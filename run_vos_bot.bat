@echo off
cd /d "%~dp0"
python vos_bot.py
if errorlevel 1 pause
