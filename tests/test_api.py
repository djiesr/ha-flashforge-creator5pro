"""CreatorReader against a local fake printer (a real aiohttp server on 127.0.0.1)."""
from __future__ import annotations

import asyncio
import copy

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer
import pytest

from api import (
    CreatorReader,
    PrinterAuthRefused,
    PrinterResponseInvalid,
    PrinterUnreachable,
    UnsupportedPrinter,
    default_camera_url,
    redact,
)
from conftest import FAKE_CHECK_CODE, FAKE_SERIAL


class FakePrinter:
    """Records every request so tests can assert nothing but /detail was sent."""

    def __init__(self, handler):
        self.requests: list[tuple[str, str, dict | None]] = []
        self._handler = handler

    async def _dispatch(self, request: web.Request) -> web.StreamResponse:
        try:
            body = await request.json()
        except Exception:
            body = None
        self.requests.append((request.method, request.path, body))
        return await self._handler(request, body)

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._dispatch)
        return app


async def _reader_for(printer: FakePrinter, *, timeout: float = 2.0):
    server = TestServer(printer.app(), host="127.0.0.1")
    await server.start_server()
    session = aiohttp.ClientSession()
    reader = CreatorReader(
        session, "127.0.0.1", FAKE_SERIAL, FAKE_CHECK_CODE, port=server.port, timeout=timeout
    )
    return server, session, reader


async def _run(handler, coro_fn, **kwargs):
    printer = FakePrinter(handler)
    server, session, reader = await _reader_for(printer, **kwargs)
    try:
        return printer, await coro_fn(reader)
    finally:
        await session.close()
        await server.close()


async def _expect(handler, exc, coro_fn=lambda r: r.async_get_status(), **kwargs):
    printer = FakePrinter(handler)
    server, session, reader = await _reader_for(printer, **kwargs)
    try:
        with pytest.raises(exc) as info:
            await coro_fn(reader)
        return printer, info.value
    finally:
        await session.close()
        await server.close()


def _assert_no_secret(text: str) -> None:
    assert FAKE_SERIAL not in text
    assert FAKE_CHECK_CODE not in text


async def test_reads_status_and_sends_only_detail(detail_printing):
    async def handler(request, body):
        return web.json_response(detail_printing)

    printer, info = await _run(handler, lambda r: r.async_validate())

    assert info.is_creator5_pro and info.pid == 41
    assert info.firmware_version == "1.9.9"
    assert info.print_bed.current == pytest.approx(60.04)
    assert len(info.tool_temps) == 4
    # Exactly one request, a POST to /detail, carrying the credentials.
    assert printer.requests == [
        ("POST", "/detail", {"serialNumber": FAKE_SERIAL, "checkCode": FAKE_CHECK_CODE})
    ]


@pytest.mark.parametrize("status", [401, 403])
async def test_http_refusal_is_auth_refused(status):
    async def handler(request, body):
        return web.Response(status=status)

    printer, err = await _expect(handler, PrinterAuthRefused)
    assert len(printer.requests) == 1
    _assert_no_secret(str(err))


async def test_nonzero_code_is_auth_refused_and_redacted():
    async def handler(request, body):
        # A printer that echoes the submitted values back must not leak them.
        return web.json_response(
            {"code": 1, "message": f"bad {FAKE_SERIAL} / {FAKE_CHECK_CODE}"}
        )

    _, err = await _expect(handler, PrinterAuthRefused)
    _assert_no_secret(str(err))
    assert "***" in str(err)


async def test_timeout_is_unreachable():
    async def handler(request, body):
        await asyncio.sleep(2)
        return web.json_response({})

    _, err = await _expect(handler, PrinterUnreachable, timeout=0.2)
    _assert_no_secret(str(err))


async def test_connection_refused_is_unreachable():
    # Grab a free port, then close the server so nothing listens on it.
    server = TestServer(web.Application(), host="127.0.0.1")
    await server.start_server()
    port = server.port
    await server.close()

    async with aiohttp.ClientSession() as session:
        reader = CreatorReader(
            session, "127.0.0.1", FAKE_SERIAL, FAKE_CHECK_CODE, port=port, timeout=2
        )
        with pytest.raises(PrinterUnreachable) as info:
            await reader.async_get_status()
    _assert_no_secret(str(info.value))


async def test_server_error_is_invalid_not_auth():
    async def handler(request, body):
        return web.Response(status=500)

    await _expect(handler, PrinterResponseInvalid)


async def test_non_json_is_invalid():
    async def handler(request, body):
        return web.Response(text="<html>nope</html>", content_type="text/html")

    await _expect(handler, PrinterResponseInvalid)


async def test_json_array_is_invalid():
    async def handler(request, body):
        return web.json_response([1, 2, 3])

    await _expect(handler, PrinterResponseInvalid)


async def test_missing_detail_is_invalid():
    async def handler(request, body):
        return web.json_response({"code": 0, "message": "Success"})

    await _expect(handler, PrinterResponseInvalid)


async def test_wrong_type_in_detail_is_invalid(detail_printing):
    data = copy.deepcopy(detail_printing)
    data["detail"]["printLayer"] = "not-a-number"

    async def handler(request, body):
        return web.json_response(data)

    await _expect(handler, PrinterResponseInvalid)


async def test_misspelled_content_type_is_accepted(detail_printing):
    """Some FlashForge firmware sends 'appliation/json'."""
    import json

    async def handler(request, body):
        return web.Response(text=json.dumps(detail_printing), content_type="appliation/json")

    _, info = await _run(handler, lambda r: r.async_get_status())
    assert info.pid == 41


@pytest.mark.parametrize("pid", [35, 36, 38, 40, None])
async def test_other_models_are_unsupported(detail_printing, pid):
    data = copy.deepcopy(detail_printing)
    data["detail"]["pid"] = pid
    data["detail"]["model"] = "Other"

    async def handler(request, body):
        return web.json_response(data)

    await _expect(handler, UnsupportedPrinter, coro_fn=lambda r: r.async_validate())


def test_redact():
    assert redact("a SECRET b", ["SECRET", "", None]) == "a *** b"


def test_default_camera_url():
    assert default_camera_url("192.0.2.10") == "http://192.0.2.10:8080/?action=stream"


# --- cancel job ---------------------------------------------------------------


async def _controller_run(handler, *, timeout: float = 2.0):
    from api import CreatorController

    printer = FakePrinter(handler)
    server = TestServer(printer.app(), host="127.0.0.1")
    await server.start_server()
    session = aiohttp.ClientSession()
    controller = CreatorController(
        session, "127.0.0.1", FAKE_SERIAL, FAKE_CHECK_CODE, port=server.port, timeout=timeout
    )
    error = None
    try:
        await controller.async_cancel_job()
    except Exception as err:  # noqa: BLE001
        error = err
    finally:
        await session.close()
        await server.close()
    return printer, error


async def test_cancel_sends_one_exact_request():
    async def handler(request, body):
        return web.json_response({"code": 0, "message": "Success"})

    printer, error = await _controller_run(handler)
    assert error is None
    assert printer.requests == [
        (
            "POST",
            "/control",
            {
                "serialNumber": FAKE_SERIAL,
                "checkCode": FAKE_CHECK_CODE,
                "payload": {"cmd": "jobCtl_cmd", "args": {"jobID": "", "action": "cancel"}},
            },
        )
    ]


async def test_cancel_timeout_is_not_retried():
    async def handler(request, body):
        await asyncio.sleep(2)
        return web.json_response({"code": 0})

    printer, error = await _controller_run(handler, timeout=0.2)
    assert isinstance(error, PrinterUnreachable)
    assert len(printer.requests) == 1


async def test_cancel_refused():
    async def handler(request, body):
        return web.json_response({"code": 1, "message": "denied"})

    printer, error = await _controller_run(handler)
    assert isinstance(error, PrinterAuthRefused)
    assert len(printer.requests) == 1


@pytest.mark.parametrize(
    ("method", "action"),
    [("async_pause_job", "pause"), ("async_resume_job", "continue"), ("async_cancel_job", "cancel")],
)
async def test_job_commands_payload(method, action):
    from api import CreatorController

    async def handler(request, body):
        return web.json_response({"code": 0})

    printer = FakePrinter(handler)
    server = TestServer(printer.app(), host="127.0.0.1")
    await server.start_server()
    async with aiohttp.ClientSession() as session:
        controller = CreatorController(
            session, "127.0.0.1", FAKE_SERIAL, FAKE_CHECK_CODE, port=server.port
        )
        await getattr(controller, method)()
    await server.close()
    assert len(printer.requests) == 1
    _, path, body = printer.requests[0]
    assert path == "/control"
    assert body["payload"] == {"cmd": "jobCtl_cmd", "args": {"jobID": "", "action": action}}
