from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtWidgets import QFrame, QScrollArea, QTabWidget, QVBoxLayout, QWidget


def add_editor_tab(tabs: QTabWidget, title: str) -> QVBoxLayout:
    """Create one scrollable settings page, matching the Telemetry editor."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(12)
    scroll.setWidget(page)
    tabs.addTab(scroll, title)
    return layout


def build_editor_tabs(
    root: QVBoxLayout,
    owner: object,
    sections: Iterable[tuple[str, Iterable[Callable[[], None]]]],
) -> QTabWidget:
    """Build consistently spaced, scrollable tabs for an overlay editor."""
    tabs = QTabWidget()
    tabs.setDocumentMode(True)
    root.addWidget(tabs, 1)
    for title, builders in sections:
        layout = add_editor_tab(tabs, title)
        # Legacy editors use either of these layout attribute names.
        setattr(owner, "content_layout", layout)
        setattr(owner, "layout_content", layout)
        for builder in builders:
            builder()
        layout.addStretch(1)
    return tabs
