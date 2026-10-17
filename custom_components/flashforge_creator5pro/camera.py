"""MJPEG camera on the printer's port 8080.

Uses Home Assistant's own MJPEG camera. Snapshots are taken from the stream.
The camera is never switched on or off from here: on the Creator 5 series the
stream control command answers "success" and does nothing (ff-5mp-hass, fw 1.9.4).
"""
from __future__ import annotations

from homeassistant.components.mjpeg.camera import MjpegCamera
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CreatorConfigEntry
from .api import default_camera_url
from .const import CONF_CAMERA_URL
from .coordinator import CreatorCoordinator
from .entity import CreatorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CreatorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    url = entry.options.get(CONF_CAMERA_URL) or default_camera_url(entry.data[CONF_HOST])
    async_add_entities([CreatorCamera(entry.runtime_data, url)])


class CreatorCamera(CreatorEntity, MjpegCamera):
    """Unavailable while the printer does not answer its status poll."""

    _attr_translation_key = "camera"

    def __init__(self, coordinator: CreatorCoordinator, url: str) -> None:
        MjpegCamera.__init__(self, mjpeg_url=url, still_image_url=None)
        CreatorEntity.__init__(self, coordinator, "camera")
