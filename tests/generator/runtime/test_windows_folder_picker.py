"""Execute the real ctypes/vtable path against synthetic OS ABI callbacks.

Not a Windows desktop test: actual Explorer display remains an OS smoke gate.
"""
import ctypes as c
import types

import pytest

from infini_local.desktop import windows_folder_picker as picker


@pytest.mark.parametrize('scenario', ['success', 's_false', 'cancel', 'init_error', 'create_error', 'options_error', 'initial_error', 'folder_error', 'result_error', 'name_error'])
def test_native_dialog_typed_abi_and_owned_resource_cleanup(monkeypatch, scenario):
    pointer = c.c_void_p
    calls, keep = [], []
    failure = -2147467259
    class Function:
        def __init__(self, callback): self.callback = callback
        def __call__(self, *args): return self.callback(*args)
    def output(out, value): c.cast(out, c.POINTER(pointer))[0] = value
    def com(label, methods):
        table = (pointer * 21)()
        for slot, (restype, argtypes, callback) in methods.items():
            function = c.CFUNCTYPE(restype, pointer, *argtypes)(callback)
            keep.append(function); table[slot] = c.cast(function, pointer)
        struct = (c.POINTER(pointer) * 1)(c.cast(table, c.POINTER(pointer)))
        keep.extend([table, struct])
        return c.cast(struct, pointer).value
    release = lambda label: (c.c_uint32, [], lambda self: calls.append('release_' + label) or 0)
    text = c.create_unicode_buffer('C:\\Folder with spaces\\Юникод'); keep.append(text)
    def name(self, mode, out):
        calls.append(('name', mode)); output(out, c.cast(text, pointer).value)
        return failure if scenario == 'name_error' else 0
    selected = com('selected', {2: release('selected'), 5: (c.c_int32, [c.c_uint32, c.POINTER(pointer)], name)})
    initial = com('initial', {2: release('initial')})
    def options(self, out):
        c.cast(out, c.POINTER(c.c_uint32))[0] = 0x1000
        return failure if scenario == 'options_error' else 0
    def set_options(self, value): calls.append(('options', value)); return 0
    def set_folder(self, value): calls.append(('folder', value)); return failure if scenario == 'folder_error' else 0
    def result(self, out):
        output(out, selected)
        return failure if scenario == 'result_error' else 0
    dialog = com('dialog', {
        2: release('dialog'), 3: (c.c_int32, [pointer], lambda self, owner: -2147023673 if scenario == 'cancel' else 0),
        9: (c.c_int32, [c.c_uint32], set_options), 10: (c.c_int32, [c.POINTER(c.c_uint32)], options),
        12: (c.c_int32, [pointer], set_folder), 20: (c.c_int32, [c.POINTER(pointer)], result),
    })
    def initialize(reserved, flags):
        calls.append(('init', flags))
        return failure if scenario == 'init_error' else 1 if scenario == 's_false' else 0
    def create(clsid, outer, context, iid, out):
        calls.append(('create', context))
        if scenario == 'create_error': return failure
        output(out, dialog); return 0
    def parse(path, binding, iid, out):
        calls.append(('initial', path)); output(out, initial)
        return failure if scenario == 'initial_error' else 0
    ole = types.SimpleNamespace(CoInitializeEx=Function(initialize), CoUninitialize=Function(lambda: calls.append('uninit')),
        CoTaskMemFree=Function(lambda value: calls.append(('free', value.value))), CoCreateInstance=Function(create))
    shell = types.SimpleNamespace(SHCreateItemFromParsingName=Function(parse))
    monkeypatch.setattr(picker, 'is_available', lambda: True)
    monkeypatch.setattr(c, 'WinDLL', lambda name, winmode: {'ole32': ole, 'shell32': shell}[name] if winmode == 0x800 else pytest.fail('Only System32 DLL loading is allowed'), raising=False)
    monkeypatch.setattr(c, 'WINFUNCTYPE', c.CFUNCTYPE, raising=False)
    if scenario.endswith('_error'):
        with pytest.raises(OSError, match='HRESULT'): picker.choose_folder('C:\\Initial folder')
    else:
        assert picker.choose_folder('C:\\Initial folder') == (None if scenario == 'cancel' else text.value)
    assert calls[0] == ('init', 6)
    assert ('uninit' in calls) == (scenario != 'init_error')
    assert ('release_dialog' in calls) == (scenario not in {'init_error', 'create_error'})
    assert ('release_initial' in calls) == (scenario not in {'init_error', 'create_error', 'options_error'})
    assert ('release_selected' in calls) == (scenario in {'success', 's_false', 'result_error', 'name_error'})
    assert any(isinstance(call, tuple) and call[0] == 'free' for call in calls) == (scenario in {'success', 's_false', 'name_error'})
    if scenario in {'success', 's_false'}:
        assert ('name', 0x80058000) in calls
        assert ('options', 0x1000 | 0x20 | 0x40 | 0x800 | 0x8 | 0x100000 | 0x2000000) in calls
        assert calls[-4:] == ['release_selected', 'release_initial', 'release_dialog', 'uninit']
    assert c.sizeof(picker._Guid) == 16
    assert ole.CoCreateInstance.restype is c.c_int32
    assert len(ole.CoCreateInstance.argtypes) == 5
