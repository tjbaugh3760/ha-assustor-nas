"""Test SNMP authentication across the client's GET and WALK paths."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pysnmp.hlapi.v3arch.asyncio import USM_AUTH_HMAC96_MD5, USM_PRIV_NONE, CommunityData, UsmUserData
from pysnmp.proto import errind
import pytest

from custom_components.ha_asustor_nas_custom_integration.api import (
    AsustorNasApiClient,
    AsustorNasAuthenticationError,
    client as api,
)

MODEL_OID = "1.3.6.1.4.1.44738.2.1.0"


@pytest.fixture
def snmp_transport(monkeypatch):
    """Intercept transport creation and capture the auth used by both requests."""
    monkeypatch.setattr(api.UdpTransportTarget, "create", AsyncMock())


@pytest.mark.usefixtures("snmp_transport")
@pytest.mark.parametrize(
    ("entry_data", "auth_type"),
    [
        ({"community": "legacy-test-community"}, CommunityData),
        (
            {"snmp_version": "3", "username": "monitor", "password": "test-passphrase", "auth_protocol": "md5"},
            UsmUserData,
        ),
    ],
)
async def test_get_and_walk_use_same_authentication(monkeypatch, entry_data, auth_type):
    requests = []

    async def get(engine, auth, *_args, **_kwargs):
        requests.append(auth)
        return None, 0, 0, []

    async def walk(engine, auth, *_args, **_kwargs):
        requests.append(auth)
        yield None, 0, 0, []

    monkeypatch.setattr(api, "get_cmd", get)
    monkeypatch.setattr(api, "walk_cmd", walk)
    hass = SimpleNamespace(async_add_executor_job=asyncio.to_thread)
    client = AsustorNasApiClient.from_config(hass, {"host": "nas.example", **entry_data})

    assert await client.async_get_data([MODEL_OID]) == {}
    assert await client.async_walk_table(MODEL_OID) == {}
    assert len(requests) == 2
    assert all(isinstance(auth, auth_type) for auth in requests)
    assert requests[0] is requests[1]
    if isinstance(requests[0], UsmUserData):
        assert requests[0].authentication_protocol == USM_AUTH_HMAC96_MD5
        assert requests[0].privacy_protocol == USM_PRIV_NONE


@pytest.mark.usefixtures("snmp_transport")
async def test_wrong_snmpv3_password_is_authentication_failure(monkeypatch):
    monkeypatch.setattr(api, "get_cmd", AsyncMock(return_value=(errind.wrongDigest, 0, 0, [])))
    hass = SimpleNamespace(async_add_executor_job=asyncio.to_thread)
    client = AsustorNasApiClient.from_config(
        hass,
        {
            "host": "nas.example",
            "snmp_version": "3",
            "username": "monitor",
            "password": "test-passphrase",
            "auth_protocol": "md5",
        },
    )

    with pytest.raises(AsustorNasAuthenticationError, match="rejected the credentials"):
        await client.async_get_data([MODEL_OID])
