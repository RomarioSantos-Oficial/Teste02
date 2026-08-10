# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec file para SectorFlow ALFA
# Gera um executável Windows (SectorFlow.exe) com todas as dependências
#
# Para usar: pyinstaller SectorFlow.spec
# Executar no Windows com Python 3.10+ e PySide6 instalado

from pathlib import Path

block_cipher = None
PROJECT_ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(PROJECT_ROOT / 'run.py')],
    pathex=[
        str(PROJECT_ROOT),
        str(PROJECT_ROOT / 'vendor/pyLMUSharedMemory'),
    ],
    binaries=[],
    datas=[
        # Imagens (logos, badges, flags, tempo, logo principal)
        (str(PROJECT_ROOT / 'images'), 'images'),
        # Dados (flags, track_maps, vehicle_catalog, online_profiles)
        (str(PROJECT_ROOT / 'data/flags'), 'data/flags'),
        (str(PROJECT_ROOT / 'data/track_maps'), 'data/track_maps'),
        (str(PROJECT_ROOT / 'data/vehicle_catalog'), 'data/vehicle_catalog'),
        (str(PROJECT_ROOT / 'data/online_profiles'), 'data/online_profiles'),
        # Configuração principal
        (str(PROJECT_ROOT / 'src/config/*.json'), 'src/config'),
        # Bibliotecas LMU (vendor)
        (str(PROJECT_ROOT / 'vendor'), 'vendor'),
    ],
    hiddenimports=[
        # PySide6 essencial
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtNetwork',
        'PySide6.QtSvg',
        'PySide6.QtPrintSupport',
        'PySide6.QtOpenGL',
        'PySide6.QtOpenGLWidgets',
        'PySide6.QtDBus',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickWidgets',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebChannel',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtWidgets',
        # Módulos internos do projeto
        'src',
        'src.telemetry',
        'src.telemetry.lmu_adapter',
        'src.telemetry.lmu_rest_client',
        'src.telemetry.lmu_rest_enrichment',
        'src.telemetry.models',
        'src.ui',
        'src.ui.main_menu_window',
        'src.ui.overlay_manager',
        'src.ui.edit_mode_manager',
        'src.tools',
        'src.tools.run_sector_flow_lmu',
        'src.config',
        'src.widget',
        'src.widget.base',
        'src.widget.battery',
        'src.widget.delta',
        'src.widget.driver_panel',
        'src.widget.flags',
        'src.widget.map',
        'src.widget.standings',
        'src.widget.tyres',
        'src.widget.weather',
        # Widgets individuais
        'src.widget.battery.battery_widget',
        'src.widget.battery.battery_editor',
        'src.widget.battery.battery_models',
        'src.widget.delta.delta_widget',
        'src.widget.delta.delta_editor',
        'src.widget.delta.delta_models',
        'src.widget.delta.delta_renderer',
        'src.widget.driver_panel.driver_panel_widget',
        'src.widget.driver_panel.driver_panel_editor',
        'src.widget.driver_panel.driver_panel_renderer',
        'src.widget.flags.flags_widget',
        'src.widget.flags.flags_editor',
        'src.widget.flags.flags_logic',
        'src.widget.flags.flags_models',
        'src.widget.flags.flags_renderer',
        'src.widget.map.map_widget',
        'src.widget.map.map_editor',
        'src.widget.map.map_builder',
        'src.widget.map.map_models',
        'src.widget.standings.standings_widget',
        'src.widget.standings.standings_editor',
        'src.widget.standings.standings_logic',
        'src.widget.standings.standings_models',
        'src.widget.standings.standings_online',
        'src.widget.standings.lmu_online_client',
        'src.widget.standings.standings_assets',
        'src.widget.tyres.tyres_widget',
        'src.widget.tyres.tyres_editor',
        'src.widget.tyres.tyres_logic',
        'src.widget.tyres.tyres_models',
        'src.widget.weather.weather_widget',
        'src.widget.weather.weather_editor',
        'src.widget.weather.weather_icons',
        'src.widget.weather.weather_models',
        'src.widget.weather.weather_predictor',
        # Dependências LMU
        'lmu_data',
        'lmu_mmap',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SectorFlow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,       # Oculta o console (aplicação GUI)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / 'images/logo/Logo.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SectorFlow',
)
