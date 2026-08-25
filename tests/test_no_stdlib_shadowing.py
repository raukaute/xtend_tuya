"""Guard against stdlib shadowing by entity-platform modules.

HA imports platform modules as attributes of the package, so a platform file
named like a stdlib module (time.py, calendar.py, ...) rebinds that name in
__init__.py's namespace after setup. A bare `import time` there then silently
becomes the platform module (this killed the 4.4.245 DP-collapse watchdog:
`time.monotonic()` raised AttributeError on every fire).

No HA import here — pure source scan of __init__.py.
"""

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "custom_components" / "xtend_tuya"


def test_init_does_not_import_module_shadowed_by_platform():
    platform_names = {p.stem for p in PKG.glob("*.py")} - {"__init__"}
    tree = ast.parse((PKG / "__init__.py").read_text())
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                if bound in platform_names:
                    offenders.append(f"line {node.lineno}: import {alias.name}")
    assert not offenders, (
        "plain `import X` in __init__.py where X is also a platform module — "
        "HA's platform import will rebind it; use `from X import ...` instead: "
        + "; ".join(offenders)
    )


if __name__ == "__main__":
    test_init_does_not_import_module_shadowed_by_platform()
    print("ok")
