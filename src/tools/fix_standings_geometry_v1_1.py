from __future__ import annotations

import py_compile
import re
import shutil
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WIDGET_PATH = (
    PROJECT_ROOT
    / "src"
    / "widget"
    / "standings"
    / "standings_widget.py"
)
TEST_PATH = (
    PROJECT_ROOT
    / "src"
    / "tools"
    / "test_standings_widget.py"
)


def backup(path: Path) -> Path:
    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    target = path.with_name(
        f"{path.name}.geometry_v1_1_{stamp}.bak"
    )
    shutil.copy2(path, target)
    print(f"Backup: {target}")
    return target


def patch_widget() -> None:
    if not WIDGET_PATH.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {WIDGET_PATH}"
        )

    source = WIDGET_PATH.read_text(
        encoding="utf-8"
    )
    original = source

    state_anchor = (
        "        self._resize_start_width = 0\n"
    )
    state_block = (
        "        self._resize_start_width = 0\n"
        "        self._render_pending = False\n"
        "        self._fitting_height = False\n"
    )

    if (
        "self._render_pending = False"
        not in source
    ):
        if state_anchor not in source:
            raise RuntimeError(
                "Não encontrei o bloco de estado "
                "do redimensionamento."
            )
        source = source.replace(
            state_anchor,
            state_block,
            1,
        )

    resize_pattern = re.compile(
        r"    def resizeEvent\("
        r"self,\s*event:\s*QResizeEvent"
        r"\)\s*->\s*None:\n"
        r"        super\(\)\.resizeEvent\(event\)\n"
        r"        self\._update_scale\(\)\n"
        r"        QTimer\.singleShot\(0,\s*self\._render\)\n",
        flags=re.MULTILINE,
    )
    resize_replacement = (
        "    def resizeEvent(\n"
        "        self,\n"
        "        event: QResizeEvent,\n"
        "    ) -> None:\n"
        "        old_width = event.oldSize().width()\n"
        "        new_width = event.size().width()\n"
        "        super().resizeEvent(event)\n"
        "        self._update_scale()\n"
        "\n"
        "        # A altura é ajustada automaticamente pelo conteúdo.\n"
        "        # Só reconstruímos a tabela quando a largura muda.\n"
        "        # Isso impede o ciclo resize -> render -> resize que\n"
        "        # gerava dezenas de avisos QWindowsWindow::setGeometry.\n"
        "        width_changed = old_width != new_width\n"
        "        if (\n"
        "            width_changed\n"
        "            and not self._fitting_height\n"
        "            and not self._render_pending\n"
        "        ):\n"
        "            self._render_pending = True\n"
        "            QTimer.singleShot(\n"
        "                0,\n"
        "                self._render_after_resize,\n"
        "            )\n"
    )

    if (
        "def _render_after_resize"
        not in source
    ):
        source, count = resize_pattern.subn(
            resize_replacement,
            source,
            count=1,
        )
        if count != 1:
            raise RuntimeError(
                "Não consegui corrigir resizeEvent."
            )

        render_anchor = (
            "    def _render(self) -> None:\n"
        )
        render_helper = (
            "    def _render_after_resize(self) -> None:\n"
            "        self._render_pending = False\n"
            "        self._render()\n"
            "\n"
        )
        if render_anchor not in source:
            raise RuntimeError(
                "Método _render não encontrado."
            )
        source = source.replace(
            render_anchor,
            render_helper + render_anchor,
            1,
        )

    fit_pattern = re.compile(
        r"    def _fit_height\(self\)\s*->\s*None:\n"
        r"        self\.root_layout\.activate\(\)\n"
        r"        desired = max\(100,\s*self\.root_layout\.sizeHint\(\)\.height\(\)\)\n"
        r"        if abs\(self\.height\(\) - desired\) > 1:\n"
        r"            self\.resize\(self\.width\(\), desired\)\n",
        flags=re.MULTILINE,
    )
    fit_replacement = (
        "    def _fit_height(self) -> None:\n"
        "        if self._fitting_height:\n"
        "            return\n"
        "\n"
        "        self.table_layout.activate()\n"
        "        self.main_layout.activate()\n"
        "        self.root_layout.activate()\n"
        "\n"
        "        desired = max(\n"
        "            1,\n"
        "            self.main_frame.sizeHint().height(),\n"
        "        )\n"
        "\n"
        "        if abs(self.height() - desired) <= 1:\n"
        "            return\n"
        "\n"
        "        self._fitting_height = True\n"
        "        try:\n"
        "            self.resize(\n"
        "                self.width(),\n"
        "                desired,\n"
        "            )\n"
        "        finally:\n"
        "            self._fitting_height = False\n"
    )

    if (
        "if self._fitting_height:"
        not in source[
            source.find(
                "    def _fit_height"
            ):
            source.find(
                "    def _preview_rows"
            )
        ]
    ):
        source, count = fit_pattern.subn(
            fit_replacement,
            source,
            count=1,
        )
        if count != 1:
            raise RuntimeError(
                "Não consegui corrigir _fit_height."
            )

    if source == original:
        print(
            "standings_widget.py já estava corrigido."
        )
    else:
        backup(WIDGET_PATH)
        WIDGET_PATH.write_text(
            source,
            encoding="utf-8",
        )
        print(
            f"Atualizado: {WIDGET_PATH}"
        )

    py_compile.compile(
        str(WIDGET_PATH),
        doraise=True,
    )


def patch_test() -> None:
    if not TEST_PATH.exists():
        print(
            "Teste visual não encontrado; "
            "correção principal já foi aplicada."
        )
        return

    source = TEST_PATH.read_text(
        encoding="utf-8"
    )
    original = source

    anchor = (
        '        self.standings = StandingsWidget("standings", config)\n'
    )
    replacement = (
        '        self.standings = StandingsWidget("standings", config)\n'
        "        # O teste abre o widget diretamente, sem passar pelo\n"
        "        # OverlayManager. Aplicamos as mesmas flags da aplicação\n"
        "        # para evitar a moldura/título padrão do Windows.\n"
        "        self.standings.setWindowFlags(\n"
        "            Qt.WindowType.FramelessWindowHint\n"
        "            | Qt.WindowType.Tool\n"
        "            | Qt.WindowType.WindowStaysOnTopHint\n"
        "        )\n"
    )

    if (
        "Qt.WindowType.FramelessWindowHint"
        not in source
    ):
        if anchor not in source:
            raise RuntimeError(
                "Criação do StandingsWidget não encontrada "
                "no teste visual."
            )
        source = source.replace(
            anchor,
            replacement,
            1,
        )

    if source == original:
        print(
            "test_standings_widget.py já estava corrigido."
        )
    else:
        backup(TEST_PATH)
        TEST_PATH.write_text(
            source,
            encoding="utf-8",
        )
        print(
            f"Atualizado: {TEST_PATH}"
        )

    py_compile.compile(
        str(TEST_PATH),
        doraise=True,
    )


def verify() -> None:
    source = WIDGET_PATH.read_text(
        encoding="utf-8"
    )
    required = {
        "controle de render pendente":
            "self._render_pending = False"
            in source,
        "controle de ajuste de altura":
            "self._fitting_height = False"
            in source,
        "render somente ao mudar largura":
            "width_changed = old_width != new_width"
            in source,
        "helper de render":
            "def _render_after_resize"
            in source,
        "altura sem ciclo":
            "self.main_frame.sizeHint().height()"
            in source,
    }
    failed = [
        label
        for label, passed in required.items()
        if not passed
    ]

    if failed:
        raise RuntimeError(
            "Verificação incompleta:\n"
            + "\n".join(
                f"  - {label}"
                for label in failed
            )
        )

    print(
        "Correção de geometria verificada."
    )
    print(
        "Sintaxe Python validada."
    )


def main() -> None:
    print(
        "Aplicando Standings Online V1.1 "
        "Geometry Hotfix..."
    )
    print()

    patch_widget()
    patch_test()
    verify()

    print()
    print(
        "Hotfix concluído corretamente."
    )
    print()
    print(
        "Execute novamente:"
    )
    print(
        r"python .\src\tools\test_standings_widget.py"
    )


if __name__ == "__main__":
    main()
