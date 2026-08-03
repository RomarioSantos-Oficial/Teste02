from __future__ import annotations
import ctypes
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LIBRARY = PROJECT_ROOT / "vendor" / "pyLMUSharedMemory"
sys.path.insert(0, str(LIBRARY))
import lmu_data
import lmu_mmap

print("=" * 70)
print("SECTOR FLOW DRIVE - INSPECAO LMU")
print("=" * 70)
print("Biblioteca:", LIBRARY)
print("MMapControl existe:", hasattr(lmu_mmap, "MMapControl"))
print("Mapa:", lmu_data.LMUConstants.LMU_SHARED_MEMORY_FILE)
print("Estrutura:", lmu_data.LMUObjectOut.__name__)
print("Tamanho:", ctypes.sizeof(lmu_data.LMUObjectOut), "bytes")
print("OK - biblioteca pronta.")
