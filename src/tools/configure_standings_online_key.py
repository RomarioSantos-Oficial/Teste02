from __future__ import annotations

import getpass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DESTINATION = (
    PROJECT_ROOT
    / "data"
    / "online_profiles"
    / "nakama_client_key.txt"
)


def main() -> None:
    print("Configuração opcional da chave cliente Nakama.")
    print("A chave não é incluída no ZIP e não aparece no diagnóstico sanitizado.")
    value = getpass.getpass("Chave cliente: ").strip()
    if not value:
        print("Nenhuma alteração realizada.")
        return
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    DESTINATION.write_text(value, encoding="utf-8")
    print(f"Chave salva localmente em: {DESTINATION}")


if __name__ == "__main__":
    main()
