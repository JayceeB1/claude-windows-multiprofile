"""In-memory winreg boundary: production code never receives a real registry handle."""
import winreg


class Key:
    def __init__(self, path):
        self.path = path
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class Registry:
    HKEY_CURRENT_USER = object()
    KEY_READ, KEY_WRITE, KEY_SET_VALUE, REG_SZ = winreg.KEY_READ, winreg.KEY_WRITE, winreg.KEY_SET_VALUE, winreg.REG_SZ

    def __init__(self, roots):
        self.roots = roots
        self.keys = {}
        self.writes = 0
        self.fail_after = None
        self.events = []

    def allowed(self, root, path):
        assert root is self.HKEY_CURRENT_USER
        assert any(path == r or path.startswith(r + '\\') for r in self.roots), 'OUT_OF_SCOPE_REGISTRY'
        self.events.append(path)

    def OpenKey(self, root, path, reserved=0, access=0):
        self.allowed(root, path)
        if path not in self.keys:
            raise FileNotFoundError()
        return Key(path)

    def CreateKeyEx(self, root, path, reserved=0, access=0):
        self.allowed(root, path)
        self.keys.setdefault(path, {})
        return Key(path)

    def QueryValueEx(self, key, name):
        if name not in self.keys[key.path]:
            raise FileNotFoundError()
        return self.keys[key.path][name]

    def end(self):
        error = OSError('ENUM_END')
        error.winerror = 259
        raise error

    def EnumValue(self, key, index):
        values = list(self.keys[key.path].items())
        if index >= len(values):
            self.end()
        name, (value, kind) = values[index]
        return name, value, kind

    def EnumKey(self, key, index):
        prefix = key.path + '\\'
        names = [p[len(prefix):] for p in self.keys if p.startswith(prefix) and '\\' not in p[len(prefix):]]
        if index >= len(names):
            self.end()
        return names[index]

    def SetValueEx(self, key, name, reserved, kind, value):
        self.writes += 1
        if self.fail_after == self.writes:
            raise OSError('INJECTED_REGISTRY_FAILURE')
        self.keys[key.path][name] = (value, kind)

    def DeleteValue(self, key, name):
        del self.keys[key.path][name]

    def DeleteKey(self, root, path):
        self.allowed(root, path)
        if any(p.startswith(path + '\\') for p in self.keys):
            raise OSError('NONEMPTY_SUBKEYS')
        del self.keys[path]
