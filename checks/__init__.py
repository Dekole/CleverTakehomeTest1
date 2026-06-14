import importlib
import pkgutil
from pathlib import Path


def load_checks():
    """Auto-discover check modules in this directory, sorted by CHECK_ID."""
    checks_dir = Path(__file__).parent
    modules = []
    for _, name, _ in pkgutil.iter_modules([str(checks_dir)]):
        module = importlib.import_module(f"checks.{name}")
        modules.append(module)
    # Sort by the first CHECK_ID (handles both str and list)
    modules.sort(key=lambda m: getattr(m, "ORDER", 99))
    return modules
