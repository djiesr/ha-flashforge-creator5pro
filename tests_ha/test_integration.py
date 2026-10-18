"""The integration loaded in a real Home Assistant test instance (printer mocked)."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.flashforge_creator5pro.api import (
    PrinterAuthRefused,
    PrinterUnreachable,
    UnsupportedPrinter,
)
from custom_components.flashforge_creator5pro.config_flow import _unique_id
from custom_components.flashforge_creator5pro.const import (
    CANCEL_ARM_SECONDS,
    CONF_CHECK_CODE,
    CONF_ENABLE_CANCEL,
    CONF_ENABLE_LIGHT,
    CONF_ENABLE_PAUSE_RESUME,
    CONF_SERIAL_NUMBER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

from .conftest import FAKE_CHECK_CODE, FAKE_HOST, FAKE_SERIAL

READER = "custom_components.flashforge_creator5pro.api.CreatorReader"

USER_INPUT = {
    CONF_HOST: FAKE_HOST,
    CONF_NAME: "Creator 5 Pro",
    CONF_SERIAL_NUMBER: FAKE_SERIAL,
    CONF_CHECK_CODE: FAKE_CHECK_CODE,
}


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Creator 5 Pro",
        unique_id=_unique_id(FAKE_SERIAL),
        data={
            CONF_HOST: FAKE_HOST,
            CONF_SERIAL_NUMBER: FAKE_SERIAL,
            CONF_CHECK_CODE: FAKE_CHECK_CODE,
        },
    )


# --- config flow ------------------------------------------------------------


async def test_user_flow_creates_entry(hass: HomeAssistant, machine_info) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    with (
        patch(f"{READER}.async_validate", AsyncMock(return_value=machine_info)) as validate,
        patch(f"{READER}.async_get_status", AsyncMock(return_value=machine_info)),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert validate.await_count == 1
    entry = result["result"]
    assert entry.unique_id == _unique_id(FAKE_SERIAL)
    assert FAKE_SERIAL not in entry.unique_id
    assert entry.title == "Creator 5 Pro"


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (PrinterAuthRefused("refused"), "invalid_auth"),
        (PrinterUnreachable("down"), "cannot_connect"),
        (UnsupportedPrinter("pid 35"), "unsupported_printer"),
    ],
)
async def test_user_flow_errors_send_one_request(hass: HomeAssistant, error, key) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(f"{READER}.async_validate", AsyncMock(side_effect=error)) as validate:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": key}
    assert validate.await_count == 1


# --- setup and entities -------------------------------------------------------


async def test_setup_creates_read_only_entities(hass: HomeAssistant, machine_info) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    with patch(f"{READER}.async_get_status", AsyncMock(return_value=machine_info)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    domains = {e.domain for e in entities}
    assert domains == {"sensor", "binary_sensor", "camera", "light"}, "only the light by default"

    def state(key: str, platform: str = "sensor"):
        entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
        assert entity_id, key
        return hass.states.get(entity_id)

    assert state("machine_status").state == "printing"
    assert state("print_progress").state == "42"
    assert float(state("bed_temperature").state) == 60.0
    assert float(state("tool_1_temperature").state) == pytest.approx(219.6)
    assert float(state("chamber_temperature").state) == pytest.approx(35.2)
    assert state("slot_2").state == "PETG"
    assert state("slot_2").attributes["active"] is True
    assert state("slot_3").state == "empty"
    assert state("printing", "binary_sensor").state == "on"
    assert state("door", "binary_sensor").state == "off"
    assert state("camera", "camera") is not None

    for s in hass.states.async_all():
        for value in (s.state, *map(str, s.attributes.values())):
            assert FAKE_SERIAL not in value and FAKE_CHECK_CODE not in value


async def test_unreachable_goes_unavailable_and_recovers(
    hass: HomeAssistant, machine_info, freezer: FrozenDateTimeFactory
) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    status = AsyncMock(return_value=machine_info)
    with patch(f"{READER}.async_get_status", status):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entity_id = er.async_get(hass).async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_bed_temperature"
        )
        assert hass.states.get(entity_id).state == "60.0"

        status.side_effect = PrinterUnreachable("No answer from printer (timeout)")
        freezer.tick(timedelta(seconds=DEFAULT_SCAN_INTERVAL + 1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

        status.side_effect = None
        freezer.tick(timedelta(seconds=DEFAULT_SCAN_INTERVAL + 1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == "60.0"


async def test_refusal_stops_polling_and_asks_reauth(
    hass: HomeAssistant, machine_info, freezer: FrozenDateTimeFactory
) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    status = AsyncMock(return_value=machine_info)
    with patch(f"{READER}.async_get_status", status):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        status.side_effect = PrinterAuthRefused("The printer refused the request (code 1)")
        freezer.tick(timedelta(seconds=DEFAULT_SCAN_INTERVAL + 1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        calls_after_refusal = status.await_count

        flows = hass.config_entries.flow.async_progress()
        assert any(f["context"]["source"] == config_entries.SOURCE_REAUTH for f in flows)

        # Ten more intervals: not a single new request.
        for _ in range(10):
            freezer.tick(timedelta(seconds=DEFAULT_SCAN_INTERVAL + 1))
            async_fire_time_changed(hass)
            await hass.async_block_till_done()
        assert status.await_count == calls_after_refusal


async def test_refusal_at_startup_does_not_retry(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    status = AsyncMock(side_effect=PrinterAuthRefused("refused"))
    with patch(f"{READER}.async_get_status", status):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.SETUP_ERROR
    assert status.await_count == 1


async def test_reauth_updates_check_code(hass: HomeAssistant, machine_info) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    with (
        patch(f"{READER}.async_validate", AsyncMock(return_value=machine_info)),
        patch(f"{READER}.async_get_status", AsyncMock(return_value=machine_info)),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_CHECK_CODE: "NEWCODE1"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_CHECK_CODE] == "NEWCODE1"


# --- cancel job ---------------------------------------------------------------

CONTROLLER = "custom_components.flashforge_creator5pro.api.CreatorController"


async def _setup_with_cancel(hass, status_mock):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Creator 5 Pro",
        unique_id=_unique_id(FAKE_SERIAL),
        data=_entry().data,
        options={CONF_ENABLE_CANCEL: True},
    )
    entry.add_to_hass(hass)
    with patch(f"{READER}.async_get_status", status_mock):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    registry = er.async_get(hass)
    switch = registry.async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_arm_cancel")
    button = registry.async_get_entity_id("button", DOMAIN, f"{entry.entry_id}_cancel_job")
    assert switch and button
    return entry, switch, button


async def _press(hass, button):
    await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)


async def test_cancel_requires_arming(hass: HomeAssistant, machine_info) -> None:
    status = AsyncMock(return_value=machine_info)
    _, switch, button = await _setup_with_cancel(hass, status)
    cancel = AsyncMock()
    with patch(f"{READER}.async_get_status", status), patch(f"{CONTROLLER}.async_cancel_job", cancel):
        with pytest.raises(ServiceValidationError):
            await _press(hass, button)
        assert cancel.await_count == 0

        await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
        assert hass.states.get(switch).state == "on"
        await _press(hass, button)
        await hass.async_block_till_done()
        assert cancel.await_count == 1
        assert hass.states.get(switch).state == "off", "one arming, one press"

        with pytest.raises(ServiceValidationError):
            await _press(hass, button)
        assert cancel.await_count == 1


async def test_arming_expires(hass: HomeAssistant, machine_info, freezer) -> None:
    status = AsyncMock(return_value=machine_info)
    _, switch, button = await _setup_with_cancel(hass, status)
    cancel = AsyncMock()
    with patch(f"{READER}.async_get_status", status), patch(f"{CONTROLLER}.async_cancel_job", cancel):
        await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
        freezer.tick(timedelta(seconds=CANCEL_ARM_SECONDS + 1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert hass.states.get(switch).state == "off"
        with pytest.raises(ServiceValidationError):
            await _press(hass, button)
    assert cancel.await_count == 0


async def test_cancel_refused_when_idle(hass: HomeAssistant, machine_info) -> None:
    from flashforge.models import MachineState

    idle = machine_info.model_copy(update={"machine_state": MachineState.READY})
    status = AsyncMock(return_value=idle)
    _, switch, button = await _setup_with_cancel(hass, status)
    cancel = AsyncMock()
    with patch(f"{READER}.async_get_status", status), patch(f"{CONTROLLER}.async_cancel_job", cancel):
        await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
        with pytest.raises(ServiceValidationError):
            await _press(hass, button)
    assert cancel.await_count == 0


async def test_cancel_no_answer_is_reported_not_retried(hass: HomeAssistant, machine_info) -> None:
    status = AsyncMock(return_value=machine_info)
    _, switch, button = await _setup_with_cancel(hass, status)
    cancel = AsyncMock(side_effect=PrinterUnreachable("No answer (timeout)"))
    with patch(f"{READER}.async_get_status", status), patch(f"{CONTROLLER}.async_cancel_job", cancel):
        await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
        with pytest.raises(HomeAssistantError):
            await _press(hass, button)
        await hass.async_block_till_done()
    assert cancel.await_count == 1



async def test_pause_resume_buttons(hass: HomeAssistant, machine_info) -> None:
    from flashforge.models import MachineState

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Creator 5 Pro",
        unique_id=_unique_id(FAKE_SERIAL),
        data=_entry().data,
        options={CONF_ENABLE_PAUSE_RESUME: True},
    )
    entry.add_to_hass(hass)
    status = AsyncMock(return_value=machine_info)  # printing
    pause, resume = AsyncMock(), AsyncMock()
    with (
        patch(f"{READER}.async_get_status", status),
        patch(f"{CONTROLLER}.async_pause_job", pause),
        patch(f"{CONTROLLER}.async_resume_job", resume),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        ids = {
            key: registry.async_get_entity_id("button", DOMAIN, f"{entry.entry_id}_{key}")
            for key in ("pause_job", "resume_job", "cancel_job")
        }
        assert ids["pause_job"] and ids["resume_job"]
        assert ids["cancel_job"] is None, "cancel has its own option"
        assert registry.async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_arm_cancel") is None

        # Printing: resume refused, pause sent once.
        with pytest.raises(ServiceValidationError):
            await _press(hass, ids["resume_job"])
        await _press(hass, ids["pause_job"])
        await hass.async_block_till_done()
        assert (pause.await_count, resume.await_count) == (1, 0)

        # Paused: pause refused, resume sent once.
        status.return_value = machine_info.model_copy(update={"machine_state": MachineState.PAUSED})
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        with pytest.raises(ServiceValidationError):
            await _press(hass, ids["pause_job"])
        await _press(hass, ids["resume_job"])
        await hass.async_block_till_done()
        assert (pause.await_count, resume.await_count) == (1, 1)



async def test_light_on_off(hass: HomeAssistant, machine_info) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    status = AsyncMock(return_value=machine_info)
    set_light = AsyncMock()
    with patch(f"{READER}.async_get_status", status), patch(f"{CONTROLLER}.async_set_light", set_light):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        light = er.async_get(hass).async_get_entity_id("light", DOMAIN, f"{entry.entry_id}_light")
        assert hass.states.get(light).state == "off"

        status.return_value = machine_info.model_copy(update={"lights_on": True})
        await hass.services.async_call("light", "turn_on", {"entity_id": light}, blocking=True)
        await hass.async_block_till_done()
        assert set_light.await_args_list[-1].args == (True,)
        assert hass.states.get(light).state == "on"

        await hass.services.async_call("light", "turn_off", {"entity_id": light}, blocking=True)
        assert set_light.await_args_list[-1].args == (False,)
        assert set_light.await_count == 2


async def test_light_can_be_hidden(hass: HomeAssistant, machine_info) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Creator 5 Pro",
        unique_id=_unique_id(FAKE_SERIAL),
        data=_entry().data,
        options={CONF_ENABLE_LIGHT: False},
    )
    entry.add_to_hass(hass)
    with patch(f"{READER}.async_get_status", AsyncMock(return_value=machine_info)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert er.async_get(hass).async_get_entity_id("light", DOMAIN, f"{entry.entry_id}_light") is None


async def test_reconfigure_changes_host_keeps_code(hass: HomeAssistant, machine_info) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    validate = AsyncMock(return_value=machine_info)
    with (
        patch(f"{READER}.async_validate", validate),
        patch(f"{READER}.async_get_status", AsyncMock(return_value=machine_info)),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.0.2.20"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "192.0.2.20"
    assert entry.data[CONF_CHECK_CODE] == FAKE_CHECK_CODE
    assert entry.data[CONF_SERIAL_NUMBER] == FAKE_SERIAL
    assert validate.await_count == 1


async def test_reconfigure_with_new_code(hass: HomeAssistant, machine_info) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    with (
        patch(f"{READER}.async_validate", AsyncMock(return_value=machine_info)),
        patch(f"{READER}.async_get_status", AsyncMock(return_value=machine_info)),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.0.2.21", CONF_CHECK_CODE: " NEWCODE2 "}
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "192.0.2.21"
    assert entry.data[CONF_CHECK_CODE] == "NEWCODE2"


async def test_reconfigure_refused_saves_nothing(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    validate = AsyncMock(side_effect=PrinterAuthRefused("refused"))
    with patch(f"{READER}.async_validate", validate):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.0.2.22", CONF_CHECK_CODE: "BADCODE"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert validate.await_count == 1
    assert entry.data[CONF_HOST] == FAKE_HOST
    assert entry.data[CONF_CHECK_CODE] == FAKE_CHECK_CODE
