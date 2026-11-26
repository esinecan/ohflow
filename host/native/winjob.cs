using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

static class WinJob
{
	const int PROCESS_TERMINATE = 0x0001;
	const int PROCESS_DUP_HANDLE = 0x0040;
	const int PROCESS_SET_QUOTA = 0x0100;
	const int DUPLICATE_SAME_ACCESS = 0x2;
	const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000;
	const int JobObjectExtendedLimitInformation = 9;
	const uint CREATE_SUSPENDED = 0x4;
	const uint CREATE_NO_WINDOW = 0x08000000;
	const int STARTF_USESTDHANDLES = 0x100;
	const uint INFINITE = 0xFFFFFFFF;

	[StructLayout(LayoutKind.Sequential)]
	struct JOBOBJECT_BASIC_LIMIT_INFORMATION
	{
		public long PerProcessUserTimeLimit;
		public long PerJobUserTimeLimit;
		public uint LimitFlags;
		public UIntPtr MinimumWorkingSetSize;
		public UIntPtr MaximumWorkingSetSize;
		public uint ActiveProcessLimit;
		public UIntPtr Affinity;
		public uint PriorityClass;
		public uint SchedulingClass;
	}

	[StructLayout(LayoutKind.Sequential)]
	struct IO_COUNTERS
	{
		public ulong ReadOperationCount;
		public ulong WriteOperationCount;
		public ulong OtherOperationCount;
		public ulong ReadTransferCount;
		public ulong WriteTransferCount;
		public ulong OtherTransferCount;
	}

	[StructLayout(LayoutKind.Sequential)]
	struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
	{
		public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
		public IO_COUNTERS IoInfo;
		public UIntPtr ProcessMemoryLimit;
		public UIntPtr JobMemoryLimit;
		public UIntPtr PeakProcessMemoryUsed;
		public UIntPtr PeakJobMemoryUsed;
	}

	[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
	struct STARTUPINFO
	{
		public int cb;
		public string lpReserved;
		public string lpDesktop;
		public string lpTitle;
		public int dwX;
		public int dwY;
		public int dwXSize;
		public int dwYSize;
		public int dwXCountChars;
		public int dwYCountChars;
		public int dwFillAttribute;
		public int dwFlags;
		public short wShowWindow;
		public short cbReserved2;
		public IntPtr lpReserved2;
		public IntPtr hStdInput;
		public IntPtr hStdOutput;
		public IntPtr hStdError;
	}

	[StructLayout(LayoutKind.Sequential)]
	struct PROCESS_INFORMATION
	{
		public IntPtr hProcess;
		public IntPtr hThread;
		public int dwProcessId;
		public int dwThreadId;
	}

	[DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
	static extern IntPtr CreateJobObjectW(IntPtr attributes, string name);

	[DllImport("kernel32.dll", SetLastError = true)]
	static extern bool SetInformationJobObject(IntPtr job, int infoClass, ref JOBOBJECT_EXTENDED_LIMIT_INFORMATION info, int length);

	[DllImport("kernel32.dll", SetLastError = true)]
	static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

	[DllImport("kernel32.dll", SetLastError = true)]
	static extern IntPtr OpenProcess(int access, bool inherit, int pid);

	[DllImport("kernel32.dll", SetLastError = true)]
	static extern bool DuplicateHandle(IntPtr sourceProcess, IntPtr source, IntPtr targetProcess, out IntPtr target, int access, bool inherit, int options);

	[DllImport("kernel32.dll")]
	static extern IntPtr GetCurrentProcess();

	[DllImport("kernel32.dll", SetLastError = true)]
	static extern bool CloseHandle(IntPtr handle);

	[DllImport("kernel32.dll", SetLastError = true)]
	static extern IntPtr GetStdHandle(int which);

	[DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
	static extern IntPtr GetCommandLineW();

	[DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
	static extern bool CreateProcessW(string application, IntPtr commandLine, IntPtr processAttributes, IntPtr threadAttributes, bool inheritHandles, uint flags, IntPtr environment, string directory, ref STARTUPINFO startup, out PROCESS_INFORMATION info);

	[DllImport("kernel32.dll", SetLastError = true)]
	static extern uint ResumeThread(IntPtr thread);

	[DllImport("kernel32.dll", SetLastError = true)]
	static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);

	[DllImport("kernel32.dll", SetLastError = true)]
	static extern bool GetExitCodeProcess(IntPtr process, out uint code);

	[DllImport("kernel32.dll", SetLastError = true)]
	static extern bool TerminateProcess(IntPtr process, uint code);

	static Exception Fail(string what)
	{
		return new Win32Exception(Marshal.GetLastWin32Error(), what);
	}

	static IntPtr KillOnCloseJob()
	{
		IntPtr job = CreateJobObjectW(IntPtr.Zero, null);
		if (job == IntPtr.Zero) throw Fail("CreateJobObject");
		SetKillOnClose(job, true);
		return job;
	}

	static void SetKillOnClose(IntPtr job, bool on)
	{
		var info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
		info.BasicLimitInformation.LimitFlags = on ? JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE : 0;
		if (!SetInformationJobObject(job, JobObjectExtendedLimitInformation, ref info, Marshal.SizeOf(info))) throw Fail("SetInformationJobObject");
	}

	static int Attach(int pid)
	{
		IntPtr process = OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE | PROCESS_DUP_HANDLE, false, pid);
		if (process == IntPtr.Zero) throw Fail("OpenProcess " + pid);
		IntPtr job = KillOnCloseJob();
		if (!AssignProcessToJobObject(job, process)) throw Fail("AssignProcessToJobObject");
		IntPtr remote;
		if (!DuplicateHandle(GetCurrentProcess(), job, process, out remote, 0, false, DUPLICATE_SAME_ACCESS)) throw Fail("DuplicateHandle");
		CloseHandle(job);
		CloseHandle(process);
		return 0;
	}

	static string ChildCommandLine()
	{
		string line = Marshal.PtrToStringUni(GetCommandLineW());
		int index = 0;
		if (line.Length > 0 && line[0] == '"')
		{
			index = line.IndexOf('"', 1);
			index = index < 0 ? line.Length : index + 1;
		}
		else
		{
			while (index < line.Length && line[index] != ' ' && line[index] != '\t') index++;
		}
		while (index < line.Length && (line[index] == ' ' || line[index] == '\t')) index++;
		if (string.CompareOrdinal(line, index, "run", 0, 3) != 0) throw new ArgumentException("expected run");
		index += 3;
		while (index < line.Length && (line[index] == ' ' || line[index] == '\t')) index++;
		if (index >= line.Length) throw new ArgumentException("run needs a program");
		return line.Substring(index);
	}

	static int Run()
	{
		string commandLine = ChildCommandLine();
		IntPtr job = KillOnCloseJob();
		var startup = new STARTUPINFO();
		startup.cb = Marshal.SizeOf(typeof(STARTUPINFO));
		startup.dwFlags = STARTF_USESTDHANDLES;
		startup.hStdInput = GetStdHandle(-10);
		startup.hStdOutput = GetStdHandle(-11);
		startup.hStdError = GetStdHandle(-12);
		IntPtr buffer = Marshal.StringToHGlobalUni(commandLine);
		PROCESS_INFORMATION child;
		bool started = CreateProcessW(null, buffer, IntPtr.Zero, IntPtr.Zero, true, CREATE_SUSPENDED | CREATE_NO_WINDOW, IntPtr.Zero, null, ref startup, out child);
		Marshal.FreeHGlobal(buffer);
		if (!started)
		{
			Console.Error.WriteLine(Fail("CreateProcess").Message);
			return 9009;
		}
		if (!AssignProcessToJobObject(job, child.hProcess))
		{
			TerminateProcess(child.hProcess, 1);
			throw Fail("AssignProcessToJobObject");
		}
		ResumeThread(child.hThread);
		CloseHandle(child.hThread);
		WaitForSingleObject(child.hProcess, INFINITE);
		uint code;
		GetExitCodeProcess(child.hProcess, out code);
		CloseHandle(child.hProcess);
		SetKillOnClose(job, false);
		CloseHandle(job);
		return unchecked((int)code);
	}

	static int Main(string[] args)
	{
		try
		{
			if (args.Length == 2 && args[0] == "attach") return Attach(int.Parse(args[1]));
			if (args.Length >= 2 && args[0] == "run") return Run();
			Console.Error.WriteLine("usage: winjob attach <pid> | winjob run <program> [args...]");
			return 2;
		}
		catch (Exception error)
		{
			Console.Error.WriteLine(error.Message);
			return 1;
		}
	}
}
