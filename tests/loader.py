"""Import scripts/validate-plugin.py by path so tests can exercise its pure functions."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate-plugin.py"
MODULE_NAME = "ds_validate_plugin"


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(MODULE_NAME, VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    # Registered before exec_module because dataclasses resolves annotations through
    # sys.modules, and this module uses `from __future__ import annotations`.
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module
