"""Ambient capture plugins package.

Plugins are self-contained capture targets. See plugin.py for the
CapturePlugin protocol and PluginCapabilities manifest.

v1 plugins (Epoch 2):
    planka_card   — creates a card in the best-matching board/list

Epoch 3 additions:
    planka_list, planka_board, calendar_event, shopping_list,
    memory_fact, reminder
"""
from app.services.ambient_capture.plugins.planka_card import PlankaCardPlugin

__all__ = ["PlankaCardPlugin"]
