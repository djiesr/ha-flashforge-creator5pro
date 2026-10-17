#!/usr/bin/env python3
"""Manual read-only test against the real printer.

Sends exactly one POST /detail (and, with --camera, one GET on the MJPEG
stream). Nothing moves, heats or starts.

Environment:
    FF_HOST        printer IP         (required)
    FF_SERIAL      serial number      (required, never printed)
    FF_CHECK_CODE  LAN check code     (required, never printed)

Exit codes:
    0 read OK          3 refused: STOP, check the code in the LAN menu
    2 config missing   4 unreachable
    5 unreadable       6 not a Creator 5 Pro      7 camera check failed
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "flashforge_creator5pro"))

import aiohttp  # noqa: E402

from api import (  # noqa: E402
    CreatorReader,
    PrinterAuthRefused,
    PrinterResponseInvalid,
    PrinterUnreachable,
    UnsupportedPrinter,
    default_camera_url,
    redact,
)
import values as v  # noqa: E402


def out(text: str, secrets: tuple[str, ...]) -> None:
    print(redact(text, secrets))


async def check_camera(session: aiohttp.ClientSession, url: str) -> tuple[bool, str]:
    """Read the first bytes of the stream and look for a JPEG start marker."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if resp.status != 200:
                return False, f"HTTP {resp.status}"
            chunk = b""
            while len(chunk) < 65536:
                part = await resp.content.read(4096)
                if not part:
                    break
                chunk += part
                if b"\xff\xd8" in chunk:
                    return True, f"HTTP 200, {ctype or 'no Content-Type'}, JPEG frame seen"
            return False, f"HTTP 200, {ctype or 'no Content-Type'}, no JPEG frame in first {len(chunk)} bytes"
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        return False, f"{type(err).__name__}: {err}"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--camera", action="store_true", help="also check the MJPEG stream on port 8080")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    host = os.environ.get("FF_HOST", "").strip()
    serial = os.environ.get("FF_SERIAL", "").strip()
    check_code = os.environ.get("FF_CHECK_CODE", "").strip()
    if not host or not serial or not check_code:
        print("FAIL: FF_HOST, FF_SERIAL and FF_CHECK_CODE must be set.", file=sys.stderr)
        return 2
    secrets = (serial, check_code)

    async with aiohttp.ClientSession() as session:
        reader = CreatorReader(session, host, serial, check_code)
        try:
            info = await reader.async_validate()
        except PrinterAuthRefused as err:
            out(f"FAIL (refused): {err}", secrets)
            print("STOP. Do not retry. Check the serial number and the check code in the "
                  "printer's LAN menu before running this again.")
            return 3
        except PrinterUnreachable as err:
            out(f"FAIL (unreachable): {err}", secrets)
            return 4
        except PrinterResponseInvalid as err:
            out(f"FAIL (unreadable answer): {err}", secrets)
            return 5
        except UnsupportedPrinter as err:
            out(f"FAIL (unsupported): {err}", secrets)
            return 6

        lines = [
            f"Model            : {info.model} (pid {info.pid}), firmware {info.firmware_version}",
            f"State            : {v.machine_state(info)} (raw status {info.status!r})",
            f"Progress         : {v.progress(info)} %, file {v.current_file(info)!r}",
            f"Layers           : {info.current_print_layer}/{info.total_print_layers}",
            f"Elapsed/remaining: {v.elapsed_seconds(info)} s / {v.remaining_seconds(info)} s",
            f"Bed              : {v.bed_temp(info)} / {v.bed_temp(info, target=True)} °C",
            f"Active nozzle    : {v.nozzle_temp(info)} / {v.nozzle_temp(info, target=True)} °C",
        ]
        for i in range(v.TOOL_COUNT):
            lines.append(f"T{i + 1}               : {v.tool_temp(info, i)} / {v.tool_temp(info, i, target=True)} °C")
        lines += [
            f"Chamber          : {v.chamber_temp(info)} / {v.chamber_temp(info, target=True)} °C "
            f"(sensor reported: {v.has_chamber(info)})",
            f"Job filament used: {info.est_length:.2f} m, {info.est_weight:.1f} g",
            f"Material station : {info.has_matl_station}, active slot {v.active_slot(info)}",
        ]
        for n in range(1, v.SLOT_COUNT + 1):
            lines.append(f"  slot {n}         : {v.slot_material(info, n)} {v.slot_attributes(info, n)}")
        lines += [
            f"Door open        : {v.door_open(info)}",
            f"Problem          : {v.has_problem(info)} (error code {info.error_code!r})",
            f"Free storage     : {v.free_disk_space_gb(info)} GB",
            f"Camera (status)  : has_camera={info.has_camera}, url={info.camera_stream_url!r}",
        ]
        for line in lines:
            out(line, secrets)
        print("READ OK")

        if args.camera:
            url = info.camera_stream_url or default_camera_url(host)
            ok, detail = await check_camera(session, url)
            out(f"Camera ({url}): {'OK' if ok else 'FAIL'} - {detail}", secrets)
            if not ok:
                return 7
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
