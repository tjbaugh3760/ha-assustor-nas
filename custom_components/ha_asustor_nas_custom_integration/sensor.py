"""Sensor platform for ASUSTOR NAS SNMP integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import PERCENTAGE, REVOLUTIONS_PER_MINUTE, UnitOfInformation, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AsustorNasDataUpdateCoordinator
from .data import AsustorNasConfigEntry
from .repairs import async_update_volume_migration_issue
from .volume_identity import migrate_volume_entities, volume_entity_key, volume_identity, volume_value_for_mount

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class AsustorNasSensorEntityDescription(SensorEntityDescription):
    """Describes an ASUSTOR NAS sensor entity."""

    value_fn: Callable[[dict[str, Any]], Any]


# Static sensors that are always present
STATIC_SENSORS: tuple[AsustorNasSensorEntityDescription, ...] = (
    AsustorNasSensorEntityDescription(
        key="model",
        name="Model",
        icon="mdi:nas",
        value_fn=lambda data: data.get("model"),
    ),
    AsustorNasSensorEntityDescription(
        key="cpu_model",
        name="CPU Model",
        icon="mdi:cpu-64-bit",
        value_fn=lambda data: data.get("cpu_model"),
    ),
    AsustorNasSensorEntityDescription(
        key="memory_total",
        name="Total Memory",
        icon="mdi:memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("memory", {}).get("total_mb"),
    ),
    AsustorNasSensorEntityDescription(
        key="memory_used",
        name="Used Memory",
        icon="mdi:memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("memory", {}).get("used_mb"),
    ),
    AsustorNasSensorEntityDescription(
        key="memory_usage_percent",
        name="Memory Usage",
        icon="mdi:percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("memory", {}).get("usage_percent"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AsustorNasConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data
    registered_volume_metrics: set[tuple[str, str]] = set()
    blocked_volume_metrics: set[tuple[str, str]] = set()
    registered_drive_metrics: set[tuple[str, str]] = set()

    blocked_volume_metrics.update(
        migrate_volume_entities(
            hass,
            entry.entry_id,
            data.get("volumes", {}),
            entry.options.get("volume_migrations", {}),
        )
    )
    async_update_volume_migration_issue(hass, entry, blocked_volume_metrics)

    entities: list[AsustorNasSensorEntity] = [
        AsustorNasSensorEntity(coordinator, entry, description)
        for description in STATIC_SENSORS
        if description.value_fn(data) is not None
    ]

    def _build_volume_entities(volume_name: str) -> list[AsustorNasSensorEntity]:
        identity = volume_identity(volume_name)
        if identity is None:
            return []
        mount_path = f"/{identity}"
        volume_descriptions = (
            AsustorNasSensorEntityDescription(
                key=volume_entity_key(identity, "total"),
                name=f"{volume_name} Total",
                icon="mdi:harddisk",
                device_class=SensorDeviceClass.DATA_SIZE,
                native_unit_of_measurement=UnitOfInformation.BYTES,
                state_class=SensorStateClass.MEASUREMENT,
                value_fn=lambda d, mount=mount_path: volume_value_for_mount(d, mount, "total_bytes"),
            ),
            AsustorNasSensorEntityDescription(
                key=volume_entity_key(identity, "used"),
                name=f"{volume_name} Used",
                icon="mdi:harddisk",
                device_class=SensorDeviceClass.DATA_SIZE,
                native_unit_of_measurement=UnitOfInformation.BYTES,
                state_class=SensorStateClass.MEASUREMENT,
                value_fn=lambda d, mount=mount_path: volume_value_for_mount(d, mount, "used_bytes"),
            ),
            AsustorNasSensorEntityDescription(
                key=volume_entity_key(identity, "free"),
                name=f"{volume_name} Free",
                icon="mdi:harddisk",
                device_class=SensorDeviceClass.DATA_SIZE,
                native_unit_of_measurement=UnitOfInformation.BYTES,
                state_class=SensorStateClass.MEASUREMENT,
                value_fn=lambda d, mount=mount_path: volume_value_for_mount(d, mount, "free_bytes"),
            ),
            AsustorNasSensorEntityDescription(
                key=volume_entity_key(identity, "usage_percent"),
                name=f"{volume_name} Usage",
                icon="mdi:percent",
                native_unit_of_measurement=PERCENTAGE,
                state_class=SensorStateClass.MEASUREMENT,
                value_fn=lambda d, mount=mount_path: volume_value_for_mount(d, mount, "usage_percent"),
            ),
        )

        new_entities = []
        for description, metric in zip(volume_descriptions, ("total", "used", "free", "usage_percent"), strict=True):
            metric_identity = (identity, metric)
            if metric_identity in blocked_volume_metrics or metric_identity in registered_volume_metrics:
                continue
            registered_volume_metrics.add(metric_identity)
            new_entities.append(AsustorNasSensorEntity(coordinator, entry, description))
        return new_entities

    def _build_new_drive_entities(data: dict[str, Any]) -> list[AsustorNasSensorEntity]:
        new_entities = []
        for drive_id, drive in data.get("drives", {}).items():
            for metric, name, icon in (
                ("smart_status", "SMART Status", "mdi:harddisk"),
                ("temperature", "Temperature", "mdi:thermometer"),
            ):
                identity = (drive_id, metric)
                if drive.get(metric) is None or identity in registered_drive_metrics:
                    continue
                is_temperature = metric == "temperature"
                description = AsustorNasSensorEntityDescription(
                    key=f"drive_{drive_id}_{metric}",
                    name=f"{drive['name']} {name}",
                    icon=icon,
                    device_class=SensorDeviceClass.TEMPERATURE if is_temperature else None,
                    native_unit_of_measurement=UnitOfTemperature.CELSIUS if is_temperature else None,
                    state_class=SensorStateClass.MEASUREMENT if is_temperature else None,
                    value_fn=lambda d, did=drive_id, field=metric: d.get("drives", {}).get(did, {}).get(field),
                )
                registered_drive_metrics.add(identity)
                new_entities.append(AsustorNasSensorEntity(coordinator, entry, description))
        return new_entities

    # 2. Add dynamic sensors (CPU Cores)
    for core_id in data.get("cpu_cores", {}):
        description = AsustorNasSensorEntityDescription(
            key=f"cpu_core_{core_id}",
            name=f"CPU Core {core_id} Usage",
            icon="mdi:speedometer",
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d, cid=core_id: d.get("cpu_cores", {}).get(cid),
        )
        entities.append(AsustorNasSensorEntity(coordinator, entry, description))

    # 3. Add dynamic sensors (Fans)
    for fan_id in data.get("fans", {}):
        description = AsustorNasSensorEntityDescription(
            key=f"fan_{fan_id}",
            name=f"Fan {fan_id}",
            icon="mdi:fan",
            native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d, fid=fan_id: d.get("fans", {}).get(fid),
        )
        entities.append(AsustorNasSensorEntity(coordinator, entry, description))

    # 4. Add dynamic sensors (Temperatures)
    for temp_id in data.get("temperatures", {}):
        name = "CPU Temperature" if temp_id == "cpu" else "System Temperature"
        icon = "mdi:thermometer" if temp_id == "cpu" else "mdi:thermometer-lines"
        description = AsustorNasSensorEntityDescription(
            key=f"temp_{temp_id}",
            name=name,
            icon=icon,
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d, tid=temp_id: d.get("temperatures", {}).get(tid),
        )
        entities.append(AsustorNasSensorEntity(coordinator, entry, description))

    # 5. Add dynamic sensors (Volumes)
    for volume_id, volume in data.get("volumes", {}).items():
        volume_id_str = str(volume_id)
        volume_name = str(volume.get("name", f"volume{volume_id_str}")).lstrip("/")
        identity = volume_identity(f"/{volume_name}")
        if identity is None:
            continue
        entities.extend(_build_volume_entities(volume_name))

    entities.extend(_build_new_drive_entities(data))
    async_add_entities(entities)

    @callback
    def _async_add_missing_storage_entities() -> None:
        new_entities = _build_new_drive_entities(coordinator.data)

        blocked_volume_metrics.clear()
        blocked_volume_metrics.update(
            migrate_volume_entities(
                hass,
                entry.entry_id,
                coordinator.data.get("volumes", {}),
                entry.options.get("volume_migrations", {}),
            )
        )
        async_update_volume_migration_issue(hass, entry, blocked_volume_metrics)

        for volume_id, volume in coordinator.data.get("volumes", {}).items():
            volume_id_str = str(volume_id)
            volume_name = str(volume.get("name", f"volume{volume_id_str}")).lstrip("/")
            identity = volume_identity(f"/{volume_name}")
            if identity is None:
                continue

            new_entities.extend(_build_volume_entities(volume_name))

        if new_entities:
            _LOGGER.debug("Adding %d new storage sensor entities", len(new_entities))
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_async_add_missing_storage_entities))


class AsustorNasSensorEntity(CoordinatorEntity[AsustorNasDataUpdateCoordinator], SensorEntity):
    """Representation of an ASUSTOR NAS sensor."""

    entity_description: AsustorNasSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AsustorNasDataUpdateCoordinator,
        entry: AsustorNasConfigEntry,
        description: AsustorNasSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry

        # Unique ID is based on the entry ID (which is tied to the MAC address) and the sensor key
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

        # Device info groups all sensors under the same NAS device
        model = coordinator.data.get("model", "Unknown")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=f"ASUSTOR NAS ({model})",
            manufacturer="ASUSTOR",
            model=model,
        )

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # The entity is available if the coordinator is successful and the value is not None
        return super().available and self.entity_description.value_fn(self.coordinator.data) is not None
