"""One execution per test contract; inherited convenience cases are not recounted."""
import importlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
CONTRACTS = (('test_workspace_inventory', 'InventoryTests'), ('test_shared_memory_plan', 'PlanTests'),
             ('test_shared_memory_apply', 'ApplyTests'), ('test_workspace_plan', 'WorkspaceTests'),
             ('test_workspace_install', 'InstallTests'), ('test_workspace_remove', 'RemoveTests'),
             ('test_workspace_entry', 'EntryTests'), ('test_native_workspace', 'NativeTests'),
             ('test_native_registry', 'RegistryTests'), ('test_native_registry_api', 'RegistryApiTests'),
             ('test_shared_config', 'SharedConfigTests'), ('test_native_reconcile', 'ReconcileTests'))
suite = unittest.TestSuite()
for module, name in CONTRACTS:
    cls = getattr(importlib.import_module(module), name)
    suite.addTests(cls(method) for method in sorted(cls.__dict__) if method.startswith('test_'))
result = unittest.TextTestRunner(verbosity=2).run(suite)
unexpected = [case.id() for case, _ in result.skipped
              if case.id() != 'test_workspace_inventory.InventoryTests.test_short_name_identity_when_available']
if unexpected:
    print('UNEXPECTED_SKIP: qualification incomplete')
    raise SystemExit(2)
print(f'QUALIFICATION: executed={result.testsRun}, passed={result.testsRun-len(result.skipped)-len(result.errors)-len(result.failures)}, '
      f'skipped={len(result.skipped)}, native_desktop=NOT_RUN')
raise SystemExit(0 if result.wasSuccessful() else 1)
