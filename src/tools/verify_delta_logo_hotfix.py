from __future__ import annotations

import inspect
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.widget.delta.delta_logo_manager import DeltaLogoManager


def main() -> None:
    signature = inspect.signature(DeltaLogoManager.match)

    print("Arquivo carregado:")
    print(inspect.getfile(DeltaLogoManager))
    print()
    print("Assinatura:")
    print(signature)

    has_varargs = any(
        parameter.kind
        is inspect.Parameter.VAR_POSITIONAL
        for parameter in signature.parameters.values()
    )

    if not has_varargs:
        raise RuntimeError(
            "ERRO: a versão antiga ainda está sendo carregada."
        )

    print()
    print("OK - o método aceita vários textos do LMU.")


if __name__ == "__main__":
    main()
