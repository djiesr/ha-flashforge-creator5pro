"""Polling coordinator for the FlashForge Creator 5 Pro."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging

from flashforge.models import FFMachineInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    CreatorController,
    PrinterAuthRefused,
    PrinterResponseInvalid,
    PrinterUnreachable,
)
from .arming import CancelArming
from .const import CANCEL_ARM_SECONDS, DOMAIN

_LOGGER = logging.getLogger(__name__)

REASON_OK = "ok"
REASON_UNREACHABLE = "unreachable"
REASON_REFUSED = "refused"
REASON_UNREADABLE = "unreadable"


class CreatorCoordinator(DataUpdateCoordinator[FFMachineInfo]):
    """Reads ``/detail`` at a fixed interval. Commands go through ``reader`` only
    from the buttons and the light, never from polling."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        reader: CreatorController,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.reader = reader
        self.arming = CancelArming(hass, CANCEL_ARM_SECONDS)
        # For the "Online" sensor: why the last poll failed, and when one last worked.
        self.connection_state: str = REASON_OK
        self.last_seen: datetime | None = None

    async def _async_update_data(self) -> FFMachineInfo:
        try:
            data = await self.reader.async_get_status()
        except PrinterAuthRefused as err:
            self.connection_state = REASON_REFUSED
            # Stops polling and opens a re-authentication flow. No automatic
            # retry: repeated refused attempts may lock the printer's LAN API.
            raise ConfigEntryAuthFailed(
                f"{err}. Polling stopped. Check the code in the printer's LAN menu."
            ) from None
        except PrinterUnreachable as err:
            self.connection_state = REASON_UNREACHABLE
            raise UpdateFailed(str(err)) from None
        except PrinterResponseInvalid as err:
            self.connection_state = REASON_UNREADABLE
            raise UpdateFailed(f"Unreadable answer from the printer: {err}") from None
        self.connection_state = REASON_OK
        self.last_seen = dt_util.utcnow()
        return data
