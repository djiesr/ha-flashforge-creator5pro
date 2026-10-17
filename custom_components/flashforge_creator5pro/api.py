"""Read-only access to a FlashForge Creator 5 Pro over the HTTP API (port 8898).

This module has no Home Assistant import, so it can be tested on its own.

Why not ``FlashForgeClient.info.get()``: in flashforge-python-api 1.6.0 that call
returns ``None`` both when the printer is unreachable and when it answers with a
non-200 status. A refused check code would then look like a network outage and
be retried on every poll, and repeated refused attempts may lock the LAN API.
This module sends the same ``POST /detail`` request itself, so it can tell the
three outcomes apart, and still uses the library to parse the answer.

``CreatorReader`` sends only ``/detail``. ``CreatorController`` adds three job
commands: cancel, pause, resume. Nothing here starts a print or sends motion or
heating commands.
"""
from __future__ import annotations

import asyncio
from collections.abc import Iterable
import json
from typing import Any

import aiohttp
from flashforge.api.controls.info import MachineInfoParser
from flashforge.models import DetailResponse, FFMachineInfo

DEFAULT_HTTP_PORT = 8898
DEFAULT_CAMERA_PORT = 8080
DEFAULT_TIMEOUT = 10.0
DETAIL_PATH = "/detail"
CONTROL_PATH = "/control"

PID_CREATOR5 = 40
PID_CREATOR5_PRO = 41

# HTTP statuses that mean "the printer refused us", as opposed to "it broke".
_AUTH_HTTP_STATUSES = frozenset({401, 403})
_OK_CODES = frozenset({0, 200})

REDACTED = "***"


class PrinterError(Exception):
    """Base class. Messages never contain the serial number or the check code."""


class PrinterUnreachable(PrinterError):
    """No answer: timeout, refused connection, DNS, network down."""


class PrinterAuthRefused(PrinterError):
    """The printer answered and refused the serial number / check code.

    Callers must stop polling on this error and never retry on their own.
    """


class PrinterResponseInvalid(PrinterError):
    """The printer answered, but the answer could not be read."""


class UnsupportedPrinter(PrinterError):
    """The printer answered, but it is not a Creator 5 Pro."""


def redact(text: str, secrets: Iterable[str | None]) -> str:
    """Replace every occurrence of each non-empty secret in ``text``."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    return text


def default_camera_url(host: str, port: int = DEFAULT_CAMERA_PORT) -> str:
    """The OEM MJPEG stream URL of the Creator 5 series."""
    return f"http://{host}:{port}/?action=stream"


def is_creator5_pro(info: FFMachineInfo) -> bool:
    """Model identity comes from the firmware-set PID, never from the user-set name."""
    return info.pid == PID_CREATOR5_PRO or bool(info.is_creator5_pro)


class CreatorReader:
    """Fetches and parses the printer status. Sends only ``/detail``."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        serial_number: str,
        check_code: str,
        *,
        port: int = DEFAULT_HTTP_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._session = session
        self._host = host
        self._serial_number = serial_number
        self._check_code = check_code
        self._base_url = f"http://{host}:{port}"
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    @property
    def host(self) -> str:
        return self._host

    def _redact(self, text: str) -> str:
        return redact(text, (self._serial_number, self._check_code))

    async def _async_post(self, path: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST once to ``path`` and return the body after checking it was accepted.

        Never retries: a command must reach the printer at most once.
        """
        payload: dict[str, Any] = {
            "serialNumber": self._serial_number,
            "checkCode": self._check_code,
        }
        if extra:
            payload.update(extra)
        try:
            async with self._session.post(
                self._base_url + path,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self._timeout,
            ) as response:
                status = response.status
                body = await response.text()
        except asyncio.TimeoutError:
            raise PrinterUnreachable(f"No answer from {self._host} (timeout)") from None
        except aiohttp.ClientError as err:
            # The exception text carries the URL and OS error, never the payload.
            raise PrinterUnreachable(
                f"Cannot reach {self._host}: {self._redact(type(err).__name__ + ': ' + str(err))}"
            ) from None

        if status in _AUTH_HTTP_STATUSES:
            raise PrinterAuthRefused(f"The printer refused the credentials (HTTP {status})")
        if status != 200:
            raise PrinterResponseInvalid(f"Unexpected HTTP status {status} from {path}")

        try:
            data = json.loads(body)
        except ValueError:
            raise PrinterResponseInvalid(f"The {path} answer is not valid JSON") from None
        if not isinstance(data, dict):
            raise PrinterResponseInvalid(
                f"The {path} answer is a {type(data).__name__}, expected an object"
            )

        code = data.get("code")
        if code not in _OK_CODES:
            # How the firmware reports a wrong check code has not been observed,
            # and must not be found out by trying. Any non-zero code is treated
            # as a refusal: stopping is the safe side.
            message = self._redact(str(data.get("message", "")))[:200]
            raise PrinterAuthRefused(
                f"The printer refused the request (code {code!r}, message {message!r})"
            )
        return data

    async def async_get_raw(self) -> dict[str, Any]:
        """Return the decoded ``/detail`` body after checking it was accepted."""
        return await self._async_post(DETAIL_PATH)

    async def async_get_status(self) -> FFMachineInfo:
        """Return the parsed status. Raises a ``PrinterError`` subclass on failure."""
        data = await self.async_get_raw()
        try:
            detail = DetailResponse(**data).detail
            info = MachineInfoParser.from_detail(detail)
        except Exception as err:  # pydantic ValidationError and parser bugs alike
            raise PrinterResponseInvalid(
                f"The /detail answer could not be parsed: {self._redact(type(err).__name__)}"
            ) from None
        if info is None:
            raise PrinterResponseInvalid("The /detail answer could not be converted")
        return info

    async def async_validate(self) -> FFMachineInfo:
        """One read used by the config flow: credentials and model check."""
        info = await self.async_get_status()
        if not is_creator5_pro(info):
            raise UnsupportedPrinter(
                f"This printer reports PID {info.pid!r} ({info.model or 'unknown model'}), "
                "not a Creator 5 Pro"
            )
        return info


class CreatorController(CreatorReader):
    """Adds the job commands exposed in Home Assistant: cancel, pause, resume.

    All three are ``jobCtl_cmd`` on ``/control`` over HTTP 8898, with the same
    payload as ``JobControl`` in flashforge-python-api 1.6.0. Cancel (which
    also backs the library's misnamed ``emergency_stop()``) is the printer's own
    job cancel, not an emergency stop: the firmware decides how motion and
    heaters wind down. Starting a print is deliberately not offered.
    """

    async def _async_job_control(self, action: str) -> None:
        await self._async_post(
            CONTROL_PATH,
            {"payload": {"cmd": "jobCtl_cmd", "args": {"jobID": "", "action": action}}},
        )

    async def async_cancel_job(self) -> None:
        """Send the cancel once. Raises a ``PrinterError`` subclass on failure."""
        await self._async_job_control("cancel")

    async def async_pause_job(self) -> None:
        await self._async_job_control("pause")

    async def async_resume_job(self) -> None:
        await self._async_job_control("continue")
