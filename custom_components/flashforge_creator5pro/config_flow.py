"""Config, re-authentication and options flows.

Each submit sends exactly one ``/detail`` request. On a refusal the form shows
an error and nothing is retried: the user must check the code in the printer's
LAN menu before submitting again.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    CreatorReader,
    PrinterAuthRefused,
    PrinterResponseInvalid,
    PrinterUnreachable,
    UnsupportedPrinter,
    default_camera_url,
)
from .const import (
    CONF_CAMERA_URL,
    CONF_CHECK_CODE,
    CONF_ENABLE_CANCEL,
    CONF_ENABLE_LIGHT,
    CONF_ENABLE_PAUSE_RESUME,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL_NUMBER,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

_SECRET = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)


def _unique_id(serial_number: str) -> str:
    """Stable per printer, without storing the serial number in clear as the ID."""
    return hashlib.sha256(serial_number.strip().encode()).hexdigest()[:16]


async def _async_try_read(hass, host: str, serial: str, check_code: str) -> str | None:
    """One read. Returns an error key, or None on success."""
    reader = CreatorReader(async_get_clientsession(hass), host, serial, check_code)
    try:
        await reader.async_validate()
    except PrinterAuthRefused as err:
        _LOGGER.warning("Printer at %s refused the credentials: %s", host, err)
        return "invalid_auth"
    except UnsupportedPrinter as err:
        _LOGGER.warning("%s", err)
        return "unsupported_printer"
    except PrinterResponseInvalid as err:
        _LOGGER.warning("Unreadable answer from %s: %s", host, err)
        return "invalid_response"
    except PrinterUnreachable as err:
        _LOGGER.info("%s", err)
        return "cannot_connect"
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Unexpected error while reading the printer at %s", host)
        return "unknown"
    return None


class CreatorConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            serial = user_input[CONF_SERIAL_NUMBER].strip()
            check_code = user_input[CONF_CHECK_CODE].strip()
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(_unique_id(serial))
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})

            error = await _async_try_read(self.hass, host, serial, check_code)
            if error is None:
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or DEFAULT_NAME,
                    data={
                        CONF_HOST: host,
                        CONF_SERIAL_NUMBER: serial,
                        CONF_CHECK_CODE: check_code,
                    },
                )
            errors["base"] = error

        defaults = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
                vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
                # Secrets are never pre-filled after an error: retyping them is
                # the moment to check them against the LAN menu.
                vol.Required(CONF_SERIAL_NUMBER): _SECRET,
                vol.Required(CONF_CHECK_CODE): _SECRET,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            check_code = user_input[CONF_CHECK_CODE].strip()
            error = await _async_try_read(
                self.hass, entry.data[CONF_HOST], entry.data[CONF_SERIAL_NUMBER], check_code
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_CHECK_CODE: check_code}
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_CHECK_CODE): _SECRET}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return CreatorOptionsFlow()


class CreatorOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = (user_input.get(CONF_CAMERA_URL) or "").strip()
            if url and not url.startswith(("http://", "https://")):
                errors[CONF_CAMERA_URL] = "invalid_url"
            else:
                return self.async_create_entry(
                    data={
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                        CONF_CAMERA_URL: url,
                        CONF_ENABLE_CANCEL: user_input.get(CONF_ENABLE_CANCEL, False),
                        CONF_ENABLE_PAUSE_RESUME: user_input.get(CONF_ENABLE_PAUSE_RESUME, False),
                        CONF_ENABLE_LIGHT: user_input.get(CONF_ENABLE_LIGHT, True),
                    }
                )

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
                vol.Optional(
                    CONF_CAMERA_URL,
                    description={
                        "suggested_value": options.get(CONF_CAMERA_URL)
                        or default_camera_url(self.config_entry.data[CONF_HOST])
                    },
                ): str,
                vol.Required(
                    CONF_ENABLE_CANCEL,
                    default=options.get(CONF_ENABLE_CANCEL, False),
                ): bool,
                vol.Required(
                    CONF_ENABLE_PAUSE_RESUME,
                    default=options.get(CONF_ENABLE_PAUSE_RESUME, False),
                ): bool,
                vol.Required(
                    CONF_ENABLE_LIGHT,
                    default=options.get(CONF_ENABLE_LIGHT, True),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
