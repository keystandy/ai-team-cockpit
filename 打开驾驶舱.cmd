@echo off
REM 启动本地控制面并打开真实 AI 团队驾驶舱
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0server\start_live.ps1"
