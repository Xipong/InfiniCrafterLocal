"""Windows' own folder dialog; no shell, Tk, or optional Python dependencies.

Call on a worker thread: that thread owns the STA, modal dialog, and COM cleanup.
IFileDialog ABI: https://learn.microsoft.com/windows/win32/api/shobjidl_core/nn-shobjidl_core-ifiledialog
"""
from __future__ import annotations

import ctypes
import os
import uuid
from typing import Any


class _Guid(ctypes.Structure):
    _fields_ = [('data1', ctypes.c_uint32), ('data2', ctypes.c_uint16),
                ('data3', ctypes.c_uint16), ('data4', ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, value: str) -> _Guid:
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def is_available() -> bool:
    return os.name == 'nt'


def _check(result: int) -> None:
    if ctypes.c_int32(result).value < 0:
        raise OSError(f'Windows folder dialog failed (HRESULT 0x{result & 0xffffffff:08x})')


def _method(pointer: ctypes.c_void_p, slot: int, result_type: Any, *argument_types: Any) -> Any:
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *argument_types)(table[slot])


def choose_folder(initial_directory: str) -> str | None:
    """Return a filesystem path or None for Cancel. Caller validates local policy."""
    if not is_available():
        raise OSError('Native folder selection is available only on Windows')
    ole = ctypes.WinDLL('ole32', winmode=0x800)
    shell = ctypes.WinDLL('shell32', winmode=0x800)
    pointer = ctypes.c_void_p
    hresult = ctypes.c_int32
    guid_pointer = ctypes.POINTER(_Guid)
    ole.CoInitializeEx.argtypes = [pointer, ctypes.c_uint32]
    ole.CoInitializeEx.restype = hresult
    ole.CoUninitialize.argtypes = []; ole.CoUninitialize.restype = None
    ole.CoTaskMemFree.argtypes = [pointer]; ole.CoTaskMemFree.restype = None
    ole.CoCreateInstance.argtypes = [guid_pointer, pointer, ctypes.c_uint32, guid_pointer, ctypes.POINTER(pointer)]
    ole.CoCreateInstance.restype = hresult
    shell.SHCreateItemFromParsingName.argtypes = [ctypes.c_wchar_p, pointer, guid_pointer, ctypes.POINTER(pointer)]
    shell.SHCreateItemFromParsingName.restype = hresult
    # COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE. S_FALSE also needs cleanup.
    _check(ole.CoInitializeEx(None, 0x2 | 0x4))
    dialog, initial, selected, name = pointer(), pointer(), pointer(), pointer()
    try:
        clsid = _Guid.parse('DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7')
        iid_dialog = _Guid.parse('D57C7288-D4AD-4768-BE02-9D969532D960')
        iid_item = _Guid.parse('43826D1E-E718-42EE-BC55-A1E261C37BFE')
        _check(ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid_dialog), ctypes.byref(dialog)))
        options = ctypes.c_uint32()
        _check(_method(dialog, 10, hresult, ctypes.POINTER(ctypes.c_uint32))(dialog, ctypes.byref(options)))
        # PICKFOLDERS | FORCEFILESYSTEM | PATHMUSTEXIST | NOCHANGEDIR |
        # NODEREFERENCELINKS | DONTADDTORECENT. No multi-select or file contents.
        _check(_method(dialog, 9, hresult, ctypes.c_uint32)(dialog, options.value | 0x20 | 0x40 | 0x800 | 0x8 | 0x100000 | 0x2000000))
        _check(shell.SHCreateItemFromParsingName(initial_directory, None, ctypes.byref(iid_item), ctypes.byref(initial)))
        _check(_method(dialog, 12, hresult, pointer)(dialog, initial))  # SetFolder
        result = _method(dialog, 3, hresult, pointer)(dialog, None)  # Show
        if result & 0xffffffff == 0x800704C7:  # HRESULT_FROM_WIN32(ERROR_CANCELLED)
            return None
        _check(result)
        _check(_method(dialog, 20, hresult, ctypes.POINTER(pointer))(dialog, ctypes.byref(selected)))  # GetResult
        _check(_method(selected, 5, hresult, ctypes.c_uint32, ctypes.POINTER(pointer))(
            selected, 0x80058000, ctypes.byref(name)))  # SIGDN_FILESYSPATH
        if not name:
            raise OSError('Windows folder dialog returned no filesystem path')
        return ctypes.wstring_at(name)
    finally:
        if name:
            ole.CoTaskMemFree(name)
        for owned in (selected, initial, dialog):
            if owned:
                _method(owned, 2, ctypes.c_uint32)(owned)  # IUnknown::Release
        ole.CoUninitialize()
