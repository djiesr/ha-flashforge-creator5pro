"""Job buttons: cancel, pause, resume. Each is created only when its option is on.

Cancel is not an emergency stop: it sends the printer's own job cancel over
HTTP 8898, and only after the arming switch is turned on. Pause and resume need
no arming. Every button checks the printer state first, sends nothing when the
command makes no sense, and sends at most once, without retry.
"""
from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
import logging
from typing import Any

from flashforge.models import FFMachineInfo

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CreatorConfigEntry
from . import values as v
from .api import CreatorController, PrinterAuthRefused, PrinterError, PrinterUnreachable
from .const import CONF_ENABLE_CANCEL, CONF_ENABLE_PAUSE_RESUME, DOMAIN
from .coordinator import CreatorCoordinator
from .entity import CreatorEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class JobButtonDescription(ButtonEntityDescription):
    option: str
    requires_arming: bool
    allowed_fn: Callable[[FFMachineInfo | None], bool]
    not_allowed_key: str
    send_fn: Callable[[CreatorController], Coroutine[Any, Any, None]]


BUTTONS: tuple[JobButtonDescription, ...] = (
    JobButtonDescription(
        key="cancel_job",
        translation_key="cancel_job",
        icon="mdi:stop-circle-outline",
        option=CONF_ENABLE_CANCEL,
        requires_arming=True,
        allowed_fn=v.can_cancel,
        not_allowed_key="cancel_no_job",
        send_fn=lambda c: c.async_cancel_job(),
    ),
    JobButtonDescription(
        key="pause_job",
        translation_key="pause_job",
        icon="mdi:pause-circle-outline",
        option=CONF_ENABLE_PAUSE_RESUME,
        requires_arming=False,
        allowed_fn=v.can_pause,
        not_allowed_key="pause_not_printing",
        send_fn=lambda c: c.async_pause_job(),
    ),
    JobButtonDescription(
        key="resume_job",
        translation_key="resume_job",
        icon="mdi:play-circle-outline",
        option=CONF_ENABLE_PAUSE_RESUME,
        requires_arming=False,
        allowed_fn=v.can_resume,
        not_allowed_key="resume_not_paused",
        send_fn=lambda c: c.async_resume_job(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CreatorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        JobButton(entry.runtime_data, d)
        for d in BUTTONS
        if entry.options.get(d.option, False)
    )


class JobButton(CreatorEntity, ButtonEntity):
    """Availability follows reachability only; validity is checked on press."""

    entity_description: JobButtonDescription

    def __init__(self, coordinator: CreatorCoordinator, description: JobButtonDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        desc = self.entity_description
        if desc.requires_arming:
            arming = self.coordinator.arming
            if not arming.armed:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="cancel_not_armed"
                )
            # One arming, one press, whatever happens next.
            arming.disarm()

        if not desc.allowed_fn(self.coordinator.data):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key=desc.not_allowed_key
            )

        _LOGGER.warning("Sending %s to the printer (requested from Home Assistant)", desc.key)
        try:
            await desc.send_fn(self.coordinator.reader)
        except PrinterUnreachable as err:
            # Unknown whether the printer received it: say so, do not resend.
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_no_answer",
                translation_placeholders={"error": str(err)},
            ) from None
        except PrinterAuthRefused as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_refused",
                translation_placeholders={"error": str(err)},
            ) from None
        except PrinterError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from None
        finally:
            await self.coordinator.async_request_refresh()

        _LOGGER.warning("The printer accepted %s", desc.key)
