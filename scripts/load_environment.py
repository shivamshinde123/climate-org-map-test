"""Load project-local environment settings without a third-party dependency.

The parser intentionally supports only the small, predictable subset this
project needs: comments, blank lines, optional ``export``, ``NAME=value``, and
matching single or double quotes.  It does not perform shell expansion.  Values
already supplied by the process environment always win over file values.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_environment(path: Path) -> int:
    """Load missing variables from ``path`` and return the number inserted.

    Malformed lines and unsafe variable names are skipped instead of executed.
    Empty values are valid; this allows the checked-in template structure to be
    copied safely while still letting callers detect missing credentials.
    """
    if not path.exists():
        return 0
    loaded = 0
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name or not name.replace("_", "").isalnum() or name[0].isdigit():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        # ``setdefault`` semantics are important for deployments, where secrets
        # injected by the host must override a developer's local file.
        if name not in os.environ:
            os.environ[name] = value
            loaded += 1
    return loaded
