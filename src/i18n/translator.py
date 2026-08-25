from __future__ import annotations

import json
import os
import re
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Signal
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QComboBox, QGroupBox, QLabel, QLineEdit,
    QMenu, QTabWidget, QWidget,
)

LANGUAGES = {
    "pt_BR": "Português (Brasil)", "en": "English", "fr": "Français",
    "es": "Español", "it": "Italiano", "de": "Deutsch",
    "zh_CN": "简体中文", "ko": "한국어", "pl": "Polski",
}

_ALIASES = {
    "brazilianportuguese": "pt_BR", "portuguese": "pt_BR", "english": "en",
    "french": "fr", "spanish": "es", "italian": "it", "german": "de",
    "chinesesimplified": "zh_CN", "chinese": "zh_CN", "korean": "ko",
    "polish": "pl",
}


def _settings_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home())
    return base / "SectorFlow" / "language.json"


def _catalog_path(language: str) -> Path:
    return Path(__file__).resolve().parent / "locales" / f"{language}.json"


def _normalise(language: str) -> str:
    value = str(language or "").strip()
    return value if value in LANGUAGES else _ALIASES.get(value.lower(), "pt_BR")


def app_language() -> str:
    try:
        data = json.loads(_settings_path().read_text(encoding="utf-8"))
        return _normalise(data.get("language", "pt_BR"))
    except (OSError, ValueError, TypeError):
        return "pt_BR"


def _load_catalog(language: str) -> dict[str, str]:
    if language == "pt_BR":
        return {}
    catalog: dict[str, str] = {}
    try:
        catalog.update(
            json.loads(_catalog_path(language).read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, TypeError):
        pass
    try:
        supplemental = json.loads(
            (_catalog_path(language).parent / "ui_supplement.json").read_text(
                encoding="utf-8"
            )
        )
        catalog.update(supplemental.get(language, {}))
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return catalog


_language = app_language()
_catalog = _load_catalog(_language)


def _build_reverse_catalog() -> dict[str, str]:
    """Mapeia qualquer tradução conhecida de volta ao texto-base português."""
    reverse: dict[str, str] = {}
    for language in LANGUAGES:
        for source, translated in _load_catalog(language).items():
            if translated and translated != source:
                reverse.setdefault(str(translated), str(source))
    return reverse


_reverse_catalog = _build_reverse_catalog()


def _source_text(text: str) -> str:
    value = str(text)
    return _reverse_catalog.get(value, value)


def tr(text: str, **values) -> str:
    source = str(text)
    translated = _catalog.get(source, source)
    if values:
        try:
            return translated.format(**values)
        except (KeyError, ValueError):
            return translated
    return translated


class RuntimeTranslator(QObject):
    language_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._translating = False

    def eventFilter(self, watched, event) -> bool:
        # Traduzir em Polish causava reentrada: alterar o texto pode polir o
        # componente novamente e disparar centenas de chamadas encadeadas.
        # Show cobre janelas e editores criados sob demanda sem esse ciclo.
        if (
            event.type() == QEvent.Type.Show
            and isinstance(watched, QWidget)
            and not self._translating
        ):
            self._translating = True
            try:
                self.translate_tree(watched)
            finally:
                self._translating = False
        return False

    @staticmethod
    def _translated(obj: QObject, key: str, current: str) -> str:
        prop = f"_sf_i18n_{key}"
        source = obj.property(prop)
        if source is None:
            source = _source_text(current)
            obj.setProperty(prop, source)
        else:
            # Versões anteriores podiam registrar coreano/italiano como texto
            # original se o aplicativo já iniciasse nesse idioma.
            source = _source_text(str(source))
            obj.setProperty(prop, source)
        return tr(str(source))

    def translate_tree(self, root) -> None:
        objects = [root]
        if isinstance(root, QObject):
            objects += root.findChildren(QObject)
        for obj in objects:
            if isinstance(obj, QWidget) and obj.windowTitle():
                obj.setWindowTitle(self._translated(obj, "title", obj.windowTitle()))
            if isinstance(obj, (QLabel, QAbstractButton)) and obj.text():
                obj.setText(self._translated(obj, "text", obj.text()))
            if isinstance(obj, QGroupBox) and obj.title():
                obj.setTitle(self._translated(obj, "group_title", obj.title()))
            if isinstance(obj, QWidget) and obj.toolTip():
                obj.setToolTip(self._translated(obj, "tip", obj.toolTip()))
            if isinstance(obj, QLineEdit) and obj.placeholderText():
                obj.setPlaceholderText(self._translated(obj, "placeholder", obj.placeholderText()))
            if isinstance(obj, QComboBox):
                for index in range(obj.count()):
                    key = f"_sf_i18n_item_{index}"
                    source = obj.property(key)
                    if source is None:
                        source = _source_text(obj.itemText(index)); obj.setProperty(key, source)
                    else:
                        source = _source_text(str(source)); obj.setProperty(key, source)
                    obj.setItemText(index, tr(str(source)))
            if isinstance(obj, QTabWidget):
                for index in range(obj.count()):
                    page = obj.widget(index); key = "_sf_i18n_tab"
                    source = page.property(key)
                    if source is None:
                        source = _source_text(obj.tabText(index)); page.setProperty(key, source)
                    else:
                        source = _source_text(str(source)); page.setProperty(key, source)
                    obj.setTabText(index, tr(str(source)))
            if isinstance(obj, QMenu):
                for action in obj.actions():
                    if action.isSeparator():
                        continue
                    source = action.property("_sf_i18n_text")
                    if source is None:
                        source = _source_text(action.text()); action.setProperty("_sf_i18n_text", source)
                    else:
                        source = _source_text(str(source)); action.setProperty("_sf_i18n_text", source)
                    action.setText(tr(str(source)))


_runtime: RuntimeTranslator | None = None


def install_translator(app: QApplication) -> RuntimeTranslator:
    global _runtime
    if _runtime is None:
        _runtime = RuntimeTranslator(app)
        app.installEventFilter(_runtime)
    return _runtime


def set_app_language(language: str) -> None:
    global _language, _catalog
    _language = _normalise(language)
    _catalog = _load_catalog(_language)
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"language": _language}, ensure_ascii=False, indent=2), encoding="utf-8")
    app = QApplication.instance()
    if app is not None and _runtime is not None:
        for widget in app.topLevelWidgets():
            _runtime.translate_tree(widget)
        _runtime.language_changed.emit(_language)
