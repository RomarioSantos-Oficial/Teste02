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
    / "flags_reference_defaults.json"
)


def backup(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    target = path.with_suffix(path.suffix + ".flags_v2.bak")
    shutil.copy2(path, target)
    print(f"Backup: {target}")


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
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)

    return result


def patch_models() -> None:
    path = PROJECT_ROOT / "src" / "telemetry" / "models.py"
    backup(path)
    source = path.read_text(encoding="utf-8")

    fields = [
        "    path_lateral_m: float = 0.0\n",
        "    track_edge_m: float = 0.0\n",
        "    speed_kmh: float = 0.0\n",
        "    pit_state: int = 0\n",
        "    individual_phase: int = 0\n",
        "    under_yellow: bool = False\n",
        "    in_garage: bool = False\n",
        "    position_in_class: int = 0\n",
        "    world_x: float = 0.0\n",
        "    world_y: float = 0.0\n",
        "    world_z: float = 0.0\n",
        "    right_x: float = 0.0\n",
        "    right_y: float = 0.0\n",
        "    right_z: float = 0.0\n",
        "    forward_x: float = 0.0\n",
        "    forward_y: float = 0.0\n",
        "    forward_z: float = 0.0\n",
    ]

    missing = [
        field
        for field in fields
        if field.strip().split(":", 1)[0] not in source
    ]

    if missing:
        marker = "    is_player: bool = False\n"

        if marker not in source:
            raise RuntimeError(
                "Não encontrei o final de DriverData em models.py."
            )

        source = source.replace(
            marker,
            "".join(missing) + marker,
            1,
        )

    session_fields = [
        "    track_length_m: float = 0.0\n",
        "    sector_flags: tuple[int, int, int] = (0, 0, 0)\n",
        "    start_light: int = 0\n",
        "    num_red_lights: int = 0\n",
        "    in_realtime: bool = False\n",
    ]
    session_missing = [
        field
        for field in session_fields
        if field.strip().split(":", 1)[0] not in source
    ]

    if session_missing:
        marker = "    game_phase: int = 0\n"

        if marker not in source:
            raise RuntimeError(
                "Não encontrei game_phase em SessionData."
            )

        source = source.replace(
            marker,
            "".join(session_missing) + marker,
            1,
        )

    path.write_text(source, encoding="utf-8")
    print(f"Atualizado: {path}")


def patch_adapter() -> None:
    path = PROJECT_ROOT / "src" / "telemetry" / "lmu_adapter.py"
    backup(path)
    source = path.read_text(encoding="utf-8")

    if "score_speed_kmh" not in source:
        marker = (
            '                last_lap = safe_float(getattr(score, "mLastLapTime", 0.0))\n\n'
            "                drivers.append(\n"
        )
        insert = (
            '                last_lap = safe_float(getattr(score, "mLastLapTime", 0.0))\n\n'
            '                score_velocity = getattr(score, "mLocalVel", None)\n'
            "                score_speed_kmh = 0.0\n"
            "                if score_velocity is not None:\n"
            "                    score_speed_kmh = math.sqrt(\n"
            "                        safe_float(score_velocity.x) ** 2\n"
            "                        + safe_float(score_velocity.y) ** 2\n"
            "                        + safe_float(score_velocity.z) ** 2\n"
            "                    ) * 3.6\n\n"
            "                score_pos = getattr(score, \"mPos\", None)\n"
            "                score_ori = getattr(score, \"mOri\", None)\n"
            "                right = score_ori[0] if score_ori is not None else None\n"
            "                forward = score_ori[2] if score_ori is not None else None\n\n"
            "                drivers.append(\n"
        )

        if marker not in source:
            raise RuntimeError(
                "Não encontrei o ponto de leitura dos carros no adapter."
            )

        source = source.replace(marker, insert, 1)

    if "world_x=safe_float" not in source:
        marker = (
            "                        lap_distance_m=safe_float(score.mLapDist),\n"
            "                        is_player=bool(score.mIsPlayer),\n"
        )
        insert = (
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
            "                        world_x=safe_float(score_pos.x) if score_pos is not None else 0.0,\n"
            "                        world_y=safe_float(score_pos.y) if score_pos is not None else 0.0,\n"
            "                        world_z=safe_float(score_pos.z) if score_pos is not None else 0.0,\n"
            "                        right_x=safe_float(right.x) if right is not None else 0.0,\n"
            "                        right_y=safe_float(right.y) if right is not None else 0.0,\n"
            "                        right_z=safe_float(right.z) if right is not None else 0.0,\n"
            "                        forward_x=safe_float(forward.x) if forward is not None else 0.0,\n"
            "                        forward_y=safe_float(forward.y) if forward is not None else 0.0,\n"
            "                        forward_z=safe_float(forward.z) if forward is not None else 0.0,\n"
            "                        is_player=bool(score.mIsPlayer),\n"
        )

        if marker not in source:
            # Previous Flags V1 may already have fields between lap distance and player.
            marker = "                        is_player=bool(score.mIsPlayer),\n"

            if marker not in source:
                raise RuntimeError(
                    "Não encontrei is_player no adapter."
                )

            insert = (
                "                        world_x=safe_float(score_pos.x) if score_pos is not None else 0.0,\n"
                "                        world_y=safe_float(score_pos.y) if score_pos is not None else 0.0,\n"
                "                        world_z=safe_float(score_pos.z) if score_pos is not None else 0.0,\n"
                "                        right_x=safe_float(right.x) if right is not None else 0.0,\n"
                "                        right_y=safe_float(right.y) if right is not None else 0.0,\n"
                "                        right_z=safe_float(right.z) if right is not None else 0.0,\n"
                "                        forward_x=safe_float(forward.x) if forward is not None else 0.0,\n"
                "                        forward_y=safe_float(forward.y) if forward is not None else 0.0,\n"
                "                        forward_z=safe_float(forward.z) if forward is not None else 0.0,\n"
                + marker
            )

        source = source.replace(marker, insert, 1)

    if "driver.position_in_class =" not in source:
        marker = (
            "            player = None\n"
            "            player_index = safe_int(telemetry.playerVehicleIdx, -1)\n"
        )
        insert = (
            "            class_positions: dict[str, int] = {}\n"
            "            for driver in sorted(\n"
            "                drivers,\n"
            "                key=lambda item: item.position or 999,\n"
            "            ):\n"
            "                class_name = driver.vehicle_class or \"UNKNOWN\"\n"
            "                class_positions[class_name] = class_positions.get(class_name, 0) + 1\n"
            "                driver.position_in_class = class_positions[class_name]\n\n"
            + marker
        )

        if marker not in source:
            raise RuntimeError(
                "Não encontrei a criação do PlayerData no adapter."
            )

        source = source.replace(marker, insert, 1)

    if "track_length_m=safe_float" not in source:
        marker = (
            "                max_laps=safe_int(info.mMaxLaps),\n"
            "                game_phase=safe_int(info.mGamePhase),\n"
        )
        insert = (
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

        if marker not in source:
            raise RuntimeError(
                "Não encontrei os dados de sessão no adapter."
            )

        source = source.replace(marker, insert, 1)

    path.write_text(source, encoding="utf-8")
    print(f"Atualizado: {path}")


def patch_registry() -> None:
    path = PROJECT_ROOT / "src" / "ui" / "widget_registry.py"
    backup(path)
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        'WidgetDefinition("flags", "Flags", "Corrida", True, False)',
        'WidgetDefinition("flags", "Flags", "Corrida", True, True)',
    )
    path.write_text(source, encoding="utf-8")
    print(f"Atualizado: {path}")


def patch_overlay_manager() -> None:
    path = PROJECT_ROOT / "src" / "ui" / "overlay_manager.py"
    backup(path)
    source = path.read_text(encoding="utf-8")

    if "from src.widget.flags.flags_widget import FlagsWidget" not in source:
        source = source.replace(
            "from src.widget.driver_panel.driver_panel_widget import DriverPanelWidget\n",
            "from src.widget.driver_panel.driver_panel_widget import DriverPanelWidget\n"
            "from src.widget.flags.flags_widget import FlagsWidget\n",
            1,
        )

    if "def create_flags(" not in source:
        marker = "    def create_widget(self, widget_id: str) -> QWidget:\n"
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
            raise RuntimeError("Não encontrei create_widget no OverlayManager.")

        source = source.replace(marker, method + marker, 1)

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

    if "flags.update_from_session(session)" not in source:
        marker = (
            "        delta = self.widgets.get(\"delta\")\n"
            "        if delta is not None and delta.isVisible():\n"
            "            delta.update_from_session(session)\n"
        )
        insert = (
            marker
            + "\n"
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
                "Não encontrei update_session_data no OverlayManager."
            )

        source = source.replace(marker, insert, 1)

    path.write_text(source, encoding="utf-8")
    print(f"Atualizado: {path}")


def patch_main_menu() -> None:
    path = PROJECT_ROOT / "src" / "ui" / "main_menu_window.py"
    backup(path)
    source = path.read_text(encoding="utf-8")

    if "from src.widget.flags.flags_editor import FlagsEditor" not in source:
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
        insert = (
            marker
            + '        elif widget_id == "flags":\n'
            '            editor = FlagsEditor(\n'
            '                deepcopy(self.overlay_manager.config_data["widgets"][widget_id]), self\n'
            '            )\n'
        )

        if marker not in source:
            raise RuntimeError("Não encontrei o editor Delta no menu.")

        source = source.replace(marker, insert, 1)

    path.write_text(source, encoding="utf-8")
    print(f"Atualizado: {path}")


def merge_config() -> None:
    path = PROJECT_ROOT / "src" / "config" / "widgets.json"
    backup(path)

    defaults = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    data = json.loads(path.read_text(encoding="utf-8"))
    current = data.setdefault("widgets", {}).get("flags", {})

    # Defaults da referência prevalecem na parte visual; posição e enabled
    # existentes são preservados.
    preserved = {
        key: current[key]
        for key in ("enabled", "monitor", "position", "size", "scale")
        if key in current
    }
    merged = deep_merge(defaults, preserved)

    data["widgets"]["flags"] = merged
    data.setdefault("defaults", {})["flags"] = deepcopy(defaults)
    data["version"] = max(int(data.get("version", 1)), 13)

    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Atualizado: {path}")


def main() -> None:
    patch_models()
    patch_adapter()
    patch_registry()
    patch_overlay_manager()
    patch_main_menu()
    merge_config()

    print()
    print("Flags V2 instalado com o mesmo desenho do arquivo de referência.")
    print()
    print("Teste:")
    print(r"python .\src\tools\test_flags_reference_widget.py")
    print()
    print("LMU:")
    print(r"python .\src\tools\run_sector_flow_lmu.py")


if __name__ == "__main__":
    main()
