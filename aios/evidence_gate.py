"""TRY-facing wrapper for the AIOS evidence promotion contract.

TRY may consume this gate; it must not redefine authority or terminal criteria.
"""
from pathlib import Path
import importlib.util

# Keep TRY independent at runtime when AIOS is vendored/available locally.
def load_aios_gate(aios_root: str | Path):
    path = Path(aios_root) / "core" / "evidence_gate.py"
    spec = importlib.util.spec_from_file_location("aios_evidence_gate", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load AIOS evidence gate: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

__all__ = ["load_aios_gate"]
