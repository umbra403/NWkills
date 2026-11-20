"""Ending the process without Qt's shutdown."""
import os
import sys


def end_process_now(exit_code: int) -> None:
    """Flushes the output and ends the process at once, skipping Python's and Qt's shutdown.

    The window self-test uses this: on the Windows build machine the process returned exit code 1 from its normal shutdown, and also from `os._exit`,
    which still unloads the DLLs. Terminating the process directly returns the code given. The checks have all passed by then, so nothing is lost."""
    sys.stdout.flush()
    sys.stderr.flush()
    if sys.platform == 'win32':
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.TerminateProcess(ctypes.c_void_p(kernel32.GetCurrentProcess()), exit_code)
    os._exit(exit_code)
