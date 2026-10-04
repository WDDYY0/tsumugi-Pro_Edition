Option Explicit

Dim WshShell, fso, ScriptDir, RootDir, PythonwPath, CmdLine
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

ScriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
RootDir = fso.GetParentFolderName(ScriptDir)

WshShell.CurrentDirectory = RootDir

If Not fso.FolderExists(RootDir & "\InPut") Then
    fso.CreateFolder(RootDir & "\InPut")
End If

PythonwPath = RootDir & "\.venv\Scripts\pythonw.exe"
If fso.FileExists(PythonwPath) Then
    CmdLine = """" & PythonwPath & """ """ & RootDir & "\tsumugi_gui_v2.py"""
    WshShell.Run CmdLine, 0, False
Else
    CmdLine = "cmd /c cd /d """ & RootDir & """ && uv run pythonw tsumugi_gui_v2.py"
    WshShell.Run CmdLine, 0, False
End If