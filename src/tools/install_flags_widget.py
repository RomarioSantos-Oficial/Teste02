from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULTS_PATH = (
    PROJECT_ROOT
    / "src"
    / "config"
    / "flags_defaults.json"
)


def backup(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {path}"
        )

    backup_path = path.with_suffix(
        path.suffix + ".flags.bak"
    )
    shutil.copy2(path, backup_path)
    print(f"Backup: {backup_path}")


def replace_once(
    path: Path,
    old: str,
    new: str,
    marker: str,
) -> None:
    source = path.read_text(encoding="utf-8")

    if marker in source:
        print(f"Já aplicado: {path.name} ({marker})")
        return

    if old not in source:
        raise RuntimeError(
            f"Não encontrei o trecho esperado em {path}.\n"
            "O arquivo local está diferente da versão do repositório."
        )

    path.write_text(
        source.replace(old, new, 1),
        encoding="utf-8",
    )
    print(f"Atualizado: {path}")


def deep_merge(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(base)

    for key, value in override.items():
        if (
            isinstance(value, dict)
            and isinstance(result.get(key), dict)
        ):
            result[key] = deep_merge(
                result[key],
                value,
            )
        else:
            result[key] = deepcopy(value)

    return result


def patch_models() -> None:
    path = (
        PROJECT_ROOT
        / "src"
        / "telemetry"
        / "models.py"
    )
    backup(path)
    source = path.read_text(encoding="utf-8")

    if "path_lateral_m: float" not in source:
        old = (
            "    lap_distance_m: float = 0.0\n"
            "    is_player: bool = False\n"
        )
        new = (
            "    lap_distance_m: float = 0.0\n"
            "    path_lateral_m: float = 0.0\n"
            "    track_edge_m: float = 0.0\n"
            "    speed_kmh: float = 0.0\n"
            "    pit_state: int = 0\n"
            "    individual_phase: int = 0\n"
            "    under_yellow: bool = False\n"
            "    in_garage: bool = False\n"
            "    position_in_class: int = 0\n"
            "    is_player: bool = False\n"
        )

        if old not in source:
            raise RuntimeError(
                "Não foi possível adicionar campos de Flags em DriverData."
            )

        source = source.replace(
            old,
            new,
            1,
        )

    if "track_length_m: float" not in source:
        old = (
            "    max_laps: int = 0\n"
            "    game_phase: int = 0\n"
        )
        new = (
            "    max_laps: int = 0\n"
            "    track_length_m: float = 0.0\n"
            "    sector_flags: tuple[int, int, int] = (0, 0, 0)\n"
            "    start_light: int = 0\n"
            "    num_red_lights: int = 0\n"
            "    in_realtime: bool = False\n"
            "    game_phase: int = 0\n"
        )

        if old not in source:
            raise RuntimeError(
                "Não foi possível adicionar campos de Flags em SessionData."
            )

        source = source.replace(
            old,
            new,
            1,
        )

    path.write_text(
        source,
        encoding="utf-8",
    )
    print(f"Atualizado: {path}")


def patch_adapter() -> None:
    path = (
        PROJECT_ROOT
        / "src"
        / "telemetry"
        / "lmu_adapter.py"
    )
    backup(path)
    source = path.read_text(encoding="utf-8")

    if "score_speed_kmh" not in source:
        old = (
            "                last_s1 = safe_float(getattr(score, \"mLastSector1\", 0.0))\n"
            "                last_s12 = safe_float(getattr(score, \"mLastSector2\", 0.0))\n"
            "                last_lap = safe_float(getattr(score, \"mLastLapTime\", 0.0))\n\n"
            "                drivers.append(\n"
        )
        new = (
            "                last_s1 = safe_float(getattr(score, \"mLastSector1\", 0.0))\n"
            "                last_s12 = safe_float(getattr(score, \"mLastSector2\", 0.0))\n"
            "                last_lap = safe_float(getattr(score, \"mLastLapTime\", 0.0))\n\n"
            "                score_velocity = getattr(score, \"mLocalVel\", None)\n"
            "                score_speed_kmh = 0.0\n"
            "                if score_velocity is not None:\n"
            "                    score_speed_kmh = math.sqrt(\n"
            "                        safe_float(score_velocity.x) ** 2\n"
            "                        + safe_float(score_velocity.y) ** 2\n"
            "                        + safe_float(score_velocity.z) ** 2\n"
            "                    ) * 3.6\n\n"
            "                drivers.append(\n"
        )

        if old not in source:
            raise RuntimeError(
                "Não foi possível adicionar cálculo de velocidade no adapter."
            )

        source = source.replace(
            old,
            new,
            1,
        )

    if "path_lateral_m=safe_float" not in source:
        old = (
            "                        lap_distance_m=safe_float(score.mLapDist),\n"
            "                        is_player=bool(score.mIsPlayer),\n"
        )
        new = (
            "                        lap_distance_m=safe_float(score.mLapDist),\n"
            "                        path_lateral_m=safe_float(\n"
            "                            getattr(score, \"mPathLateral\", 0.0)\n"
            "                        ),\n"
            "                        track_edge_m=safe_float(\n"
            "                            getattr(score, \"mTrackEdge\", 0.0)\n"
            "                        ),\n"
            "                        speed_kmh=score_speed_kmh,\n"
            "                        pit_state=safe_int(\n"
            "                            getattr(score, \"mPitState\", 0)\n"
            "                        ),\n"
            "                        individual_phase=safe_int(\n"
            "                            getattr(score, \"mIndividualPhase\", 0)\n"
            "                        ),\n"
            "                        under_yellow=bool(\n"
            "                            getattr(score, \"mUnderYellow\", False)\n"
            "                        ),\n"
            "                        in_garage=bool(\n"
            "                            getattr(score, \"mInGarageStall\", False)\n"
            "                        ),\n"
            "                        is_player=bool(score.mIsPlayer),\n"
        )

        if old not in source:
            raise RuntimeError(
                "Não foi possível adicionar dados dos carros no adapter."
            )

        source = source.replace(
            old,
            new,
            1,
        )

    if "position_in_class = class_positions" not in source:
        old = (
            "            player = None\n"
            "            player_index = safe_int(telemetry.playerVehicleIdx, -1)\n"
        )
        new = (
            "            class_positions: dict[str, int] = {}\n"
            "            for driver in sorted(\n"
            "                drivers,\n"
            "                key=lambda item: item.position or 999,\n"
            "            ):\n"
            "                class_name = driver.vehicle_class or \"UNKNOWN\"\n"
            "                class_positions[class_name] = (\n"
            "                    class_positions.get(class_name, 0) + 1\n"
            "                )\n"
            "                driver.position_in_class = class_positions[class_name]\n\n"
            "            player = None\n"
            "            player_index = safe_int(telemetry.playerVehicleIdx, -1)\n"
        )

        if old not in source:
            raise RuntimeError(
                "Não foi possível calcular posição na categoria."
            )

        source = source.replace(
            old,
            new,
            1,
        )

    if "track_length_m=safe_float" not in source:
        old = (
            "                max_laps=safe_int(info.mMaxLaps),\n"
            "                game_phase=safe_int(info.mGamePhase),\n"
        )
        new = (
            "                max_laps=safe_int(info.mMaxLaps),\n"
            "                track_length_m=safe_float(\n"
            "                    getattr(info, \"mLapDist\", 0.0)\n"
            "                ),\n"
            "                sector_flags=tuple(\n"
            "                    safe_int(value)\n"
            "                    for value in list(\n"
            "                        getattr(info, \"mSectorFlag\", (0, 0, 0))\n"
            "                    )[:3]\n"
            "                ),\n"
            "                start_light=safe_int(\n"
            "                    getattr(info, \"mStartLight\", 0)\n"
            "                ),\n"
            "                num_red_lights=safe_int(\n"
            "                    getattr(info, \"mNumRedLights\", 0)\n"
            "                ),\n"
            "                in_realtime=bool(\n"
            "                    getattr(info, \"mInRealtime\", False)\n"
            "                ),\n"
            "                game_phase=safe_int(info.mGamePhase),\n"
        )

        if old not in source:
            raise RuntimeError(
                "Não foi possível adicionar dados de sessão no adapter."
            )

        source = source.replace(
            old,
            new,
            1,
        )

    path.write_text(
        source,
        encoding="utf-8",
    )
    print(f"Atualizado: {path}")


def patch_registry() -> None:
    path = (
        PROJECT_ROOT
        / "src"
        / "ui"
        / "widget_registry.py"
    )
    backup(path)
    source = path.read_text(encoding="utf-8")
    old = (
        'WidgetDefinition("flags", "Flags", "Corrida", True, False)'
    )
    new = (
        'WidgetDefinition("flags", "Flags", "Corrida", True, True)'
    )

    if old in source:
        source = source.replace(
            old,
            new,
            1,
        )
    elif new not in source:
        raise RuntimeError(
            "Definição de Flags não encontrada no registry."
        )

    path.write_text(
        source,
        encoding="utf-8",
    )
    print(f"Atualizado: {path}")


def patch_overlay_manager() -> None:
    path = (
        PROJECT_ROOT
        / "src"
        / "ui"
        / "overlay_manager.py"
    )
    backup(path)
    source = path.read_text(encoding="utf-8")

    if (
        "from src.widget.flags.flags_widget import FlagsWidget"
        not in source
    ):
        source = source.replace(
            "from src.widget.driver_panel.driver_panel_widget import DriverPanelWidget\n",
            "from src.widget.driver_panel.driver_panel_widget import DriverPanelWidget\n"
            "from src.widget.flags.flags_widget import FlagsWidget\n",
            1,
        )

    if "def create_flags(" not in source:
        marker = (
            "    def create_widget(self, widget_id: str) -> QWidget:\n"
        )
        method = (
            "    def create_flags(self) -> FlagsWidget:\n"
            "        existing = self.widgets.get(\"flags\")\n"
            "        if isinstance(existing, FlagsWidget):\n"
            "            return existing\n"
            "        config = deepcopy(self.config_data[\"widgets\"][\"flags\"])\n"
            "        widget = FlagsWidget(\"flags\", config)\n"
            "        self._prepare_widget(\"flags\", widget, config)\n"
            "        return widget\n\n"
        )

        if marker not in source:
            raise RuntimeError(
                "Ponto de criação de Flags não encontrado."
            )

        source = source.replace(
            marker,
            method + marker,
            1,
        )

    if '"flags": self.create_flags' not in source:
        source = source.replace(
            '            "delta": self.create_delta,\n',
            '            "delta": self.create_delta,\n'
            '            "flags": self.create_flags,\n',
            1,
        )

    source = source.replace(
        'widget_id in {"driver_panel", "delta"}',
        'widget_id in {"driver_panel", "delta", "flags"}',
    )

    if 'flags.update_from_session(session)' not in source:
        marker = (
            "        delta = self.widgets.get(\"delta\")\n"
            "        if delta is not None and delta.isVisible():\n"
            "            delta.update_from_session(session)\n"
        )
        replacement = (
            marker
            + "\n"
            "        # Flags pode se ocultar automaticamente quando a pista\n"
            "        # está limpa. Mesmo oculto, ele precisa continuar\n"
            "        # recebendo telemetria para reaparecer sozinho.\n"
            "        flags = self.widgets.get(\"flags\")\n"
            "        flags_config = self.config_data.get(\"widgets\", {}).get(\n"
            "            \"flags\", {}\n"
            "        )\n"
            "        if flags is not None and bool(\n"
            "            flags_config.get(\"enabled\", False)\n"
            "        ):\n"
            "            flags.update_from_session(session)\n"
        )

        if marker not in source:
            raise RuntimeError(
                "Ponto de atualização da sessão não encontrado."
            )

        source = source.replace(
            marker,
            replacement,
            1,
        )

    path.write_text(
        source,
        encoding="utf-8",
    )
    print(f"Atualizado: {path}")


def patch_main_menu() -> None:
    path = (
        PROJECT_ROOT
        / "src"
        / "ui"
        / "main_menu_window.py"
    )
    backup(path)
    source = path.read_text(encoding="utf-8")

    if (
        "from src.widget.flags.flags_editor import FlagsEditor"
        not in source
    ):
        source = source.replace(
            "from src.widget.driver_panel.driver_panel_editor import DriverPanelEditor\n",
            "from src.widget.driver_panel.driver_panel_editor import DriverPanelEditor\n"
            "from src.widget.flags.flags_editor import FlagsEditor\n",
            1,
        )

    if 'elif widget_id == "flags":' not in source:
        marker = (
            '        elif widget_id == "delta":\n'
            '            editor = DeltaEditor(\n'
            '                deepcopy(self.overlay_manager.config_data["widgets"][widget_id]), self\n'
            '            )\n'
        )
        replacement = (
            marker
            + '        elif widget_id == "flags":\n'
            '            editor = FlagsEditor(\n'
            '                deepcopy(self.overlay_manager.config_data["widgets"][widget_id]), self\n'
            '            )\n'
        )

        if marker not in source:
            raise RuntimeError(
                "Ponto do editor Delta não encontrado no menu."
            )

        source = source.replace(
            marker,
            replacement,
            1,
        )

    path.write_text(
        source,
        encoding="utf-8",
    )
    print(f"Atualizado: {path}")


def merge_config() -> None:
    widgets_path = (
        PROJECT_ROOT
        / "src"
        / "config"
        / "widgets.json"
    )
    backup(widgets_path)

    defaults = json.loads(
        DEFAULTS_PATH.read_text(
            encoding="utf-8"
        )
    )
    data = json.loads(
        widgets_path.read_text(
            encoding="utf-8"
        )
    )
    current = (
        data
        .setdefault("widgets", {})
        .get("flags", {})
    )
    data["widgets"]["flags"] = deep_merge(
        defaults,
        current,
    )
    data.setdefault(
        "defaults",
        {},
    )["flags"] = deepcopy(defaults)
    data["version"] = max(
        int(data.get("version", 1)),
        12,
    )

    widgets_path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Atualizado: {widgets_path}")


def main() -> None:
    patch_models()
    patch_adapter()
    patch_registry()
    patch_overlay_manager()
    patch_main_menu()
    merge_config()

    print()
    print("Flags V1 instalado.")
    print()
    print("Teste sem o LMU:")
    print(r"python .\src\tools\test_flags_widget.py")
    print()
    print("Executar com o LMU:")
    print(r"python .\src\tools\run_sector_flow_lmu.py")


if __name__ == "__main__":
    main()
