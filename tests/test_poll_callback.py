"""An interrupted poll must give the notification handler back to its caller."""

import asyncio
from unittest.mock import Mock

import pytest
from bleak import BleakClient

from custom_components.private_jack.lib.ble_client import JackeryBleClient
from custom_components.private_jack.lib.commands import CommandBuilder
from custom_components.private_jack.lib.crypto import AutoDetectEncryption


@pytest.mark.asyncio
@pytest.mark.parametrize("auto_detect", [False, True])
@pytest.mark.parametrize("cancel", [False, True])
async def test_interrupted_poll_restores_notification_handler(auto_detect, cancel):
    jackery = JackeryBleClient()
    jackery.client = Mock(spec=BleakClient, is_connected=True)
    if auto_detect:
        jackery.encryption = Mock(spec=AutoDetectEncryption, detected_type=None)
        jackery.encryption.get_encryption_types.return_value = ["test"]
        jackery.encryption.encrypt_with_type.return_value = "00"

    handler = Mock()
    jackery.set_notification_callback(handler)
    written = asyncio.Event()

    async def write(*args, **kwargs):
        written.set()
        if not cancel:
            raise RuntimeError("write failed")

    jackery.client.write_gatt_char.side_effect = write
    poll = asyncio.create_task(jackery.send_command_collect_all(CommandBuilder().query_device_property()))
    await asyncio.wait_for(written.wait(), timeout=1)
    if cancel:
        poll.cancel()
        with pytest.raises(asyncio.CancelledError):
            await poll
    else:
        with pytest.raises(RuntimeError, match="write failed"):
            await poll

    jackery._parse_and_callback_raw(b'{"rb":80}'.hex())
    handler.assert_called_once_with({"rb": 80})
