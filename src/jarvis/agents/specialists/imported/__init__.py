"""Auto-imported skills from Claude Code."""
from pathlib import Path
import importlib
import pkgutil

__all__ = []

for _, module_name, _ in pkgutil.iter_modules([str(Path(__file__).parent)]):
    if module_name in ('ai', 'data', 'design', 'dev', 'finance', 'ops', 'other', 'research', 'test', 'writing'):
        try:
            module = importlib.import_module('jarvis.agents.specialists.imported.' + module_name)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and attr_name.endswith('Agent') and attr_name != 'BaseAgent':
                    globals()[attr_name] = attr
                    __all__.append(attr_name)
        except Exception:
            pass
