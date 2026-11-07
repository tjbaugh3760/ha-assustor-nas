"""Custom integration to integrate ASUSTOR NAS with Home Assistant."""

from __future__ import annotations

from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant

from .api import AsustorNasApiClient
from .const import DEFAULT_SCAN_INTERVAL
from .coordinator import AsustorNasDataUpdateCoordinator
from .data import AsustorNasConfigEntry, AsustorNasData
from .repairs import async_remove_volume_migration_issue

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AsustorNasConfigEntry,
) -> bool:
    """Set up this integration using UI."""
    # Initialize client
    client = AsustorNasApiClient.from_config(hass, entry.data)

    # Initialize coordinator
    coordinator = AsustorNasDataUpdateCoordinator(
        hass=hass,
        client=client,
        update_interval=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    # Store runtime data
    entry.runtime_data = AsustorNasData(
        client=client,
        coordinator=coordinator,
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: AsustorNasConfigEntry) -> None:
    """Reload after options update so explicit volume choices take effect."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant,
    entry: AsustorNasConfigEntry,
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: AsustorNasConfigEntry) -> None:
    """Remove the issue after the user permanently removes this NAS entry."""
    async_remove_volume_migration_issue(hass, entry)
