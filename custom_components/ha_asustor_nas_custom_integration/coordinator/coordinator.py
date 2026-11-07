"""Coordinator for ASUSTOR NAS SNMP integration."""

from collections import Counter
from contextlib import suppress
from datetime import timedelta
import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ..api import AsustorNasApiClient, AsustorNasAuthenticationError, AsustorNasConnectionError
from ..const import (
    DOMAIN,
    OID_ASUSTOR_CPU_CORE_USAGE_BASE,
    OID_ASUSTOR_CPU_MODEL,
    OID_ASUSTOR_DISK_ENTRY_BASE,
    OID_ASUSTOR_FAN_RPM_BASE,
    OID_ASUSTOR_MODEL,
    OID_ASUSTOR_TEMP_CPU,
    OID_ASUSTOR_TEMP_SYS,
    OID_HR_FS_MOUNT_POINT,
    OID_HR_FS_STORAGE_INDEX,
    OID_HR_FS_TABLE_BASE,
    OID_HR_STORAGE_ALLOCATION_UNITS,
    OID_HR_STORAGE_DESCR,
    OID_HR_STORAGE_FIXED_DISK,
    OID_HR_STORAGE_SIZE,
    OID_HR_STORAGE_TABLE_BASE,
    OID_HR_STORAGE_TYPE,
    OID_HR_STORAGE_USED,
    OID_MEM_AVAIL,
    OID_MEM_BUFFER,
    OID_MEM_CACHED,
    OID_MEM_TOTAL,
)

_LOGGER = logging.getLogger(__name__)
VOLUME_MOUNT_PATTERN = re.compile(r"^/volume\d+$")


def _decode_hex_string(hex_str: str) -> str:
    """Decode a hex string returned by SNMP."""
    hex_str = hex_str.strip()

    hex_str = hex_str.removeprefix("0x")

    normalized = "".join(hex_str.split())

    if normalized and len(normalized) % 2 == 0 and all(char in "0123456789abcdefABCDEF" for char in normalized):
        try:
            return bytes.fromhex(normalized).decode("utf-8", errors="replace").rstrip("\x00").strip()
        except ValueError:
            return hex_str

    return hex_str


def _process_drive_data(disk_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Correlate disk-table columns by row and identify sensors by ADM disk ID."""
    rows: dict[str, dict[str, Any]] = {}
    columns = {"2": "name", "6": "smart_status", "7": "temperature"}
    prefix = f"{OID_ASUSTOR_DISK_ENTRY_BASE}."
    for oid, value in disk_data.items():
        if not oid.startswith(prefix):
            continue
        column, _, index = oid.removeprefix(prefix).partition(".")
        if column in columns and index.isdecimal():
            rows.setdefault(index, {})[columns[column]] = value

    drives = []
    for row in rows.values():
        name = _decode_hex_string(str(row.get("name") or ""))
        if not name:
            continue
        status = _decode_hex_string(str(row.get("smart_status") or ""))
        drive = {"name": name, "smart_status": status or None, "temperature": None}
        with suppress(TypeError, ValueError):
            drive["temperature"] = int(row.get("temperature"))
        drives.append((name.casefold(), drive))

    counts = Counter(identity for identity, _ in drives)
    return {identity: drive for identity, drive in drives if counts[identity] == 1}


class AsustorNasDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching ASUSTOR NAS data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: AsustorNasApiClient,
        update_interval: int,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        try:
            # 1. Fetch static and single-row data
            static_oids = [
                OID_ASUSTOR_MODEL,
                OID_ASUSTOR_CPU_MODEL,
                OID_ASUSTOR_TEMP_CPU,
                OID_ASUSTOR_TEMP_SYS,
                OID_MEM_TOTAL,
                OID_MEM_AVAIL,
                OID_MEM_BUFFER,
                OID_MEM_CACHED,
            ]
            static_data = await self.client.async_get_data(static_oids)

            # 2. Fetch tabular data (walks)
            cpu_cores_data = await self.client.async_walk_table(OID_ASUSTOR_CPU_CORE_USAGE_BASE)
            fans_data = await self.client.async_walk_table(OID_ASUSTOR_FAN_RPM_BASE)
            storage_data = await self.client.async_walk_table(OID_HR_STORAGE_TABLE_BASE)
            fs_data = await self.client.async_walk_table(OID_HR_FS_TABLE_BASE)
            disk_data = await self.client.async_walk_table(OID_ASUSTOR_DISK_ENTRY_BASE)

        except AsustorNasAuthenticationError as exception:
            raise ConfigEntryAuthFailed(exception) from exception
        except AsustorNasConnectionError as exception:
            raise UpdateFailed(exception) from exception

        processed = self._process_data(static_data, cpu_cores_data, fans_data, storage_data, fs_data)
        processed["drives"] = _process_drive_data(disk_data)
        return processed

    # Keep indexed SNMP table correlation and aggregation together so cross-table row mapping stays explicit.
    def _process_data(  # noqa: C901
        self,
        static_data: dict[str, Any],
        cpu_cores_data: dict[str, Any],
        fans_data: dict[str, Any],
        storage_data: dict[str, Any],
        fs_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Process raw SNMP data into a structured dictionary."""
        processed: dict[str, Any] = {
            "model": static_data.get(OID_ASUSTOR_MODEL, "Unknown"),
            "cpu_model": _decode_hex_string(str(static_data.get(OID_ASUSTOR_CPU_MODEL, ""))),
            "temperatures": {},
            "memory": {},
            "cpu_cores": {},
            "fans": {},
            "volumes": {},
        }

        # Temperatures
        if OID_ASUSTOR_TEMP_CPU in static_data:
            with suppress(ValueError):
                processed["temperatures"]["cpu"] = int(static_data[OID_ASUSTOR_TEMP_CPU])

        if OID_ASUSTOR_TEMP_SYS in static_data:
            with suppress(ValueError):
                processed["temperatures"]["system"] = int(static_data[OID_ASUSTOR_TEMP_SYS])

        # Memory (Standard Linux UCD-SNMP-MIB)
        try:
            mem_total = int(static_data.get(OID_MEM_TOTAL, 0))
            mem_avail = int(static_data.get(OID_MEM_AVAIL, 0))
            mem_buffer = int(static_data.get(OID_MEM_BUFFER, 0))
            mem_cached = int(static_data.get(OID_MEM_CACHED, 0))

            if mem_total > 0:
                mem_used = max(mem_total - (mem_avail + mem_buffer + mem_cached), 0)
                mem_usage_percent = (mem_used / mem_total) * 100

                # Convert kB to MB for Home Assistant native DATA_SIZE handling
                mem_total_mb = mem_total / 1024
                mem_used_mb = mem_used / 1024

                processed["memory"] = {
                    "total_mb": round(mem_total_mb, 2),
                    "used_mb": round(mem_used_mb, 2),
                    "usage_percent": round(mem_usage_percent, 2),
                }
        except ValueError:
            _LOGGER.warning("Failed to parse memory data")

        # CPU Cores
        # Sort OIDs to ensure stable ordering (Core 1, Core 2, etc.)
        # We sort by the numeric value of the last segment of the OID to map
        # raw SNMP indices (e.g. 196608) to logical indices (e.g. 1).
        sorted_cpu_items = []
        for oid, value in cpu_cores_data.items():
            try:
                # Extract last part as integer for sorting
                idx = int(oid.split(".")[-1])
                sorted_cpu_items.append((idx, value))
            except ValueError:
                continue

        sorted_cpu_items.sort(key=lambda x: x[0])

        for i, (_, value) in enumerate(sorted_cpu_items, start=1):
            processed["cpu_cores"][str(i)] = int(value)

        # Fans
        # Sort OIDs to ensure stable ordering
        sorted_fan_items = []
        for oid, value in fans_data.items():
            try:
                idx = int(oid.split(".")[-1])
                sorted_fan_items.append((idx, value))
            except ValueError:
                continue

        sorted_fan_items.sort(key=lambda x: x[0])

        for i, (_, value) in enumerate(sorted_fan_items, start=1):
            processed["fans"][str(i)] = int(value)

        # Volumes (HOST-RESOURCES-MIB)
        storage_rows: dict[str, dict[str, Any]] = {}
        for oid, value in storage_data.items():
            oid_str = str(oid)
            idx = _extract_index(oid_str, OID_HR_STORAGE_TYPE, "hrStorageType")
            if idx is not None:
                storage_rows.setdefault(idx, {})["type"] = str(value)
                continue

            idx = _extract_index(oid_str, OID_HR_STORAGE_DESCR, "hrStorageDescr")
            if idx is not None:
                storage_rows.setdefault(idx, {})["descr"] = str(value)
                continue

            idx = _extract_index(oid_str, OID_HR_STORAGE_ALLOCATION_UNITS, "hrStorageAllocationUnits")
            if idx is not None:
                parsed_value = _parse_int_value(value)
                if parsed_value is not None:
                    storage_rows.setdefault(idx, {})["alloc_units"] = parsed_value
                continue

            idx = _extract_index(oid_str, OID_HR_STORAGE_SIZE, "hrStorageSize")
            if idx is not None:
                parsed_value = _parse_int_value(value)
                if parsed_value is not None:
                    storage_rows.setdefault(idx, {})["size"] = parsed_value
                continue

            idx = _extract_index(oid_str, OID_HR_STORAGE_USED, "hrStorageUsed")
            if idx is not None:
                parsed_value = _parse_int_value(value)
                if parsed_value is not None:
                    storage_rows.setdefault(idx, {})["used"] = parsed_value

        fs_mount_points: dict[str, str] = {}
        fs_storage_indexes: dict[str, int] = {}
        for oid, value in fs_data.items():
            oid_str = str(oid)

            idx = _extract_index(oid_str, OID_HR_FS_MOUNT_POINT, "hrFSMountPoint")
            if idx is not None:
                fs_mount_points[idx] = str(value).strip('"')
                continue

            idx = _extract_index(oid_str, OID_HR_FS_STORAGE_INDEX, "hrFSStorageIndex")
            if idx is not None:
                parsed_value = _parse_int_value(value)
                if parsed_value is not None:
                    fs_storage_indexes[idx] = parsed_value

        storage_to_mount: dict[str, str] = {}
        for fs_idx, storage_idx in fs_storage_indexes.items():
            mount_point = fs_mount_points.get(fs_idx)
            if mount_point:
                storage_to_mount[str(storage_idx)] = mount_point

        for storage_idx, row in storage_rows.items():
            storage_type = str(row.get("type", ""))
            if "hrStorageFixedDisk" not in storage_type and storage_type != OID_HR_STORAGE_FIXED_DISK:
                continue

            mount_point = storage_to_mount.get(storage_idx, str(row.get("descr", ""))).strip('"')
            if not VOLUME_MOUNT_PATTERN.fullmatch(mount_point):
                continue

            if mount_point == "/volume0":
                continue

            alloc_units = row.get("alloc_units")
            size = row.get("size")
            used = row.get("used")
            if not isinstance(alloc_units, int) or not isinstance(size, int) or not isinstance(used, int):
                continue

            total_bytes = alloc_units * size
            used_bytes = alloc_units * used
            free_bytes = max(total_bytes - used_bytes, 0)
            usage_percent = (used_bytes / total_bytes) * 100 if total_bytes > 0 else 0

            processed["volumes"][storage_idx] = {
                "name": mount_point,
                "total_bytes": total_bytes,
                "used_bytes": used_bytes,
                "free_bytes": free_bytes,
                "usage_percent": round(usage_percent, 2),
            }

        _LOGGER.debug(
            "Processed %d storage rows and exposed %d root volumes", len(storage_rows), len(processed["volumes"])
        )

        return processed


def _extract_index(oid: str, numeric_prefix: str, symbolic_name: str) -> str | None:
    """Extract row index from numeric or symbolic table OID."""
    if oid.startswith(f"{numeric_prefix}."):
        return oid.rsplit(".", 1)[-1]

    symbolic_token = f"{symbolic_name}."
    if symbolic_token in oid:
        return oid.rsplit(".", 1)[-1]

    return None


def _parse_int_value(value: Any) -> int | None:
    """Parse integer-like SNMP values, including forms like '4096 Bytes'."""
    raw = str(value).strip()
    token = raw.split(maxsplit=1)[0] if raw else ""

    with suppress(ValueError):
        return int(token)

    return None
