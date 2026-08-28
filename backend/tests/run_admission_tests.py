import sys, importlib.util, traceback
sys.path.insert(0, '/app/tests')
sys.path.insert(0, '/app')

spec = importlib.util.spec_from_file_location('t', '/app/tests/test_admission_console_guards.py')
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)

passed = failed = 0
failures = []
for name in dir(t):
    obj = getattr(t, name)
    if name.startswith('test_') and callable(obj):
        try:
            obj()
            passed += 1
        except Exception:
            failed += 1
            failures.append((name, traceback.format_exc()))
print(f'{passed} passed, {failed} failed')
for name, tb in failures:
    print('=' * 60)
    print(name)
    print(tb)
sys.exit(1 if failed else 0)
