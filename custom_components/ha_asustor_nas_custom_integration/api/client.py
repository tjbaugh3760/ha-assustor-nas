"""API Client for ASUSTOR NAS SNMP integration."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import logging
import socket
from typing import Any

from pysnmp.error import PySnmpError
from pysnmp.hlapi.v3arch.asyncio import (
    USM_AUTH_HMAC96_MD5,
    USM_AUTH_HMAC96_SHA,
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    get_cmd,
    walk_cmd,
)
from pysnmp.proto import errind
from pysnmp.proto.rfc1905 import NoSuchInstance, NoSuchObject

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant

from ..const import CONF_AUTH_PROTOCOL, CONF_COMMUNITY, CONF_SNMP_VERSION, DEFAULT_COMMUNITY, DEFAULT_PORT, SNMP_V3

_LOGGER = logging.getLogger(__name__)


class AsustorNasApiClientError(Exception):
    """Base exception for API errors."""


class AsustorNasConnectionError(AsustorNasApiClientError):
    """Exception for connection errors."""


class AsustorNasAuthenticationError(AsustorNasApiClientError):
    """Exception for authentication errors."""


AUTH_PROTOCOLS = {"md5": USM_AUTH_HMAC96_MD5, "sha": USM_AUTH_HMAC96_SHA}
AUTH_ERRORS = (
    errind.AuthenticationError,
    errind.AuthenticationFailure,
    errind.UnknownUserName,
    errind.UnsupportedSecurityLevel,
    errind.WrongDigest,
)


def _raise_snmp_error(error: errind.ErrorIndication) -> None:
    """Report authentication failures without logging credentials."""
    if isinstance(error, AUTH_ERRORS) or str(error) in {"authorizationError", "unknownCommunityName"}:
        raise AsustorNasAuthenticationError("SNMP rejected the credentials or security level")
    raise AsustorNasConnectionError(f"SNMP error: {error}")


class AsustorNasApiClient:
    """API Client for ASUSTOR NAS via SNMP."""

    def __init__(
        self, hass: HomeAssistant, host: str, auth: CommunityData | UsmUserData, port: int = DEFAULT_PORT
    ) -> None:
        """Initialize the API client."""
        self.hass = hass
        self.host = host
        self.auth = auth
        self.port = port
        # Do NOT initialize SnmpEngine here, as it performs blocking I/O (reads MIB files).
        # It must be initialized inside the executor thread.

    @classmethod
    def from_config(cls, hass: HomeAssistant, data: Mapping[str, Any]) -> AsustorNasApiClient:
        """Use SNMPv3 credentials or preserve SNMPv2c for legacy entries."""
        if data.get(CONF_SNMP_VERSION) == SNMP_V3:
            auth = UsmUserData(
                data[CONF_USERNAME],
                authKey=data[CONF_PASSWORD],
                authProtocol=AUTH_PROTOCOLS[data[CONF_AUTH_PROTOCOL]],
            )
        else:
            auth = CommunityData(data.get(CONF_COMMUNITY, DEFAULT_COMMUNITY), mpModel=1)
        return cls(hass, data[CONF_HOST], auth, data.get(CONF_PORT, DEFAULT_PORT))

    def _get_data_sync(self, oids: list[str]) -> dict[str, Any]:
        """Get data for specific OIDs synchronously."""

        async def _run_async() -> dict[str, Any]:
            # Initialize engine in the executor thread to avoid blocking the event loop
            snmp_engine = SnmpEngine()
            transport = await UdpTransportTarget.create((self.host, self.port), timeout=5, retries=1)

            try:
                error_indication, error_status, error_index, var_binds = await get_cmd(
                    snmp_engine,
                    self.auth,
                    transport,
                    ContextData(),
                    *[ObjectType(ObjectIdentity(oid)) for oid in oids],
                    lookupMib=False,
                )
            finally:
                snmp_engine.close_dispatcher()

            if error_indication:
                _raise_snmp_error(error_indication)

            if error_status:
                if error_status.prettyPrint() == "authorizationError":
                    raise AsustorNasAuthenticationError("SNMP denied access to the requested object")
                raise AsustorNasApiClientError(
                    f"SNMP error status: {error_status.prettyPrint()} at "
                    f"{(error_index and var_binds[int(error_index) - 1][0]) or '?'}"
                )

            result = {}
            for name, val in var_binds:
                # Use str(name) to get the pure numeric OID string (e.g., "1.3.6.1.4.1.44738.2.1.0")
                # instead of name.prettyPrint() which might return "SNMPv2-SMI::enterprises..."
                if not isinstance(val, (NoSuchObject, NoSuchInstance)):
                    result[str(name)] = val.prettyPrint()

            return result

        try:
            return asyncio.run(_run_async())
        except (TimeoutError, socket.gaierror, PySnmpError) as err:
            raise AsustorNasConnectionError(f"Connection error to {self.host}: {err}") from err
        except Exception as err:
            if isinstance(err, AsustorNasApiClientError):
                raise
            raise AsustorNasApiClientError(f"Unexpected error: {err}") from err

    def _walk_table_sync(self, base_oid: str) -> dict[str, Any]:
        """Walk an SNMP table synchronously and return the results."""

        async def _run_async() -> dict[str, Any]:
            # Initialize engine in the executor thread to avoid blocking the event loop
            snmp_engine = SnmpEngine()
            transport = await UdpTransportTarget.create((self.host, self.port), timeout=5, retries=1)
            result = {}

            try:
                async for error_indication, error_status, error_index, var_binds in walk_cmd(
                    snmp_engine,
                    self.auth,
                    transport,
                    ContextData(),
                    ObjectType(ObjectIdentity(base_oid)),
                    lexicographicMode=False,
                    lookupMib=False,
                ):
                    if error_indication:
                        _raise_snmp_error(error_indication)

                    if error_status:
                        if error_status.prettyPrint() == "authorizationError":
                            raise AsustorNasAuthenticationError("SNMP denied access to the requested object")
                        raise AsustorNasApiClientError(
                            f"SNMP error status: {error_status.prettyPrint()} at "
                            f"{(error_index and var_binds[int(error_index) - 1][0]) or '?'}"
                        )

                    for name, val in var_binds:
                        result[str(name)] = val.prettyPrint()
            finally:
                snmp_engine.close_dispatcher()

            return result

        try:
            return asyncio.run(_run_async())
        except (TimeoutError, socket.gaierror, PySnmpError) as err:
            raise AsustorNasConnectionError(f"Connection error walking {base_oid} on {self.host}: {err}") from err
        except Exception as err:
            if isinstance(err, AsustorNasApiClientError):
                raise
            raise AsustorNasApiClientError(f"Unexpected error walking {base_oid}: {err}") from err

    async def async_get_data(self, oids: list[str]) -> dict[str, Any]:
        """Get data for specific OIDs asynchronously."""
        return await self.hass.async_add_executor_job(self._get_data_sync, oids)

    async def async_walk_table(self, base_oid: str) -> dict[str, Any]:
        """Walk an SNMP table asynchronously and return the results."""
        return await self.hass.async_add_executor_job(self._walk_table_sync, base_oid)
