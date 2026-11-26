' run-hidden.vbs: start a console program with no console window, wait, return its exit code.
'
' Usage:
'   wscript.exe //B //Nologo run-hidden.vbs <program> [arguments...]
'
' wscript.exe is a GUI-subsystem program and gets no console. Run(..., 0, True) starts
' <program> with its console hidden, waits for it, and returns its exit code. Children of
' <program> share the hidden console and open no window either. ohflow's detach.py starts
' its WMI launch script through this file. OHFLOW_RUN_HIDDEN names another copy.
'
' //B suppresses the modal Windows Script Host error dialog. Exit 127 means <program> did
' not start. An argument that contains a space is quoted again; an argument must not
' contain a double quote.
Option Explicit
Dim shell, cmd, i, arg, rc

If WScript.Arguments.Count = 0 Then WScript.Quit 2

cmd = ""
For i = 0 To WScript.Arguments.Count - 1
    arg = WScript.Arguments(i)
    If arg = "" Or InStr(arg, " ") > 0 Or InStr(arg, vbTab) > 0 Then arg = """" & arg & """"
    If i > 0 Then cmd = cmd & " "
    cmd = cmd & arg
Next

Set shell = CreateObject("WScript.Shell")
On Error Resume Next
rc = shell.Run(cmd, 0, True)
If Err.Number <> 0 Then WScript.Quit 127
On Error GoTo 0
WScript.Quit rc
