Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Find Python: embedded in resources or system
pythonExe = ""
embeddedPy = strDir & "\resources\python\python\python.exe"
If fso.FileExists(embeddedPy) Then
    pythonExe = embeddedPy
ElseIf fso.FileExists(strDir & "\python\python.exe") Then
    pythonExe = strDir & "\python\python.exe"
Else
    ' Try system Python
    On Error Resume Next
    pythonExe = WshShell.RegRead("HKLM\SOFTWARE\Python\PythonCore\3.12\InstallPath\ExecutablePath")
    If Err.Number <> 0 Then
        pythonExe = "python"
        Err.Clear
    End If
    On Error GoTo 0
End If

' Find backend directory
backendDir = ""
If fso.FileExists(strDir & "\resources\backend\main.py") Then
    backendDir = strDir & "\resources\backend"
ElseIf fso.FileExists(strDir & "\backend\main.py") Then
    backendDir = strDir & "\backend"
End If

If pythonExe <> "" And backendDir <> "" Then
    WshShell.CurrentDirectory = backendDir
    WshShell.Run """" & pythonExe & """ """ & backendDir & "\main.py""", 0, False
    WScript.Sleep 3000
End If

' Start Electron app
exePath = ""
If fso.FileExists(strDir & "\小土豆AI桌宠.exe") Then
    exePath = strDir & "\小土豆AI桌宠.exe"
ElseIf fso.FileExists(strDir & "\PotatoPet.exe") Then
    exePath = strDir & "\PotatoPet.exe"
Else
    For Each f In fso.GetFolder(strDir).Files
        If LCase(fso.GetExtensionName(f.Path)) = "exe" And InStr(LCase(f.Name), "potato") > 0 Then
            exePath = f.Path
            Exit For
        End If
    Next
End If

If exePath <> "" Then
    WshShell.Run """" & exePath & """", 1, False
Else
    MsgBox "找不到小土豆启动程序", vbExclamation, "错误"
End If
