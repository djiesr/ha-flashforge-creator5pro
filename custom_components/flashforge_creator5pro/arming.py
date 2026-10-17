"""Arming state for the cancel button: the explicit confirmation step."""
from __future__ import annotations

from collections.abc import Callable

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later


class CancelArming:
    """Armed for a few seconds, then disarmed on its own. Never persisted."""

    def __init__(self, hass: HomeAssistant, seconds: float) -> None:
        self._hass = hass
        self._seconds = seconds
        self._armed = False
        self._timer: CALLBACK_TYPE | None = None
        self._listeners: list[Callable[[], None]] = []

    @property
    def armed(self) -> bool:
        return self._armed

    @callback
    def arm(self) -> None:
        self._cancel_timer()
        self._armed = True
        self._timer = async_call_later(self._hass, self._seconds, self._expire)
        self._notify()

    @callback
    def disarm(self) -> None:
        self._cancel_timer()
        if self._armed:
            self._armed = False
            self._notify()

    @callback
    def add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(listener)

        @callback
        def _remove() -> None:
            self._listeners.remove(listener)

        return _remove

    @callback
    def _expire(self, _now) -> None:
        self._timer = None
        self.disarm()

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer()
            self._timer = None

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()
