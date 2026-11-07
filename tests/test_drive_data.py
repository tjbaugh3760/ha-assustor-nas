"""Test discovery using the ASUSTOR disk table."""

from custom_components.ha_asustor_nas_custom_integration.coordinator.coordinator import _process_drive_data

DISK_ENTRY = "1.3.6.1.4.1.44738.4.1.1"


def test_drive_identity_survives_snmp_row_changes():
    first = {
        f"{DISK_ENTRY}.2.1": "Disk0",
        f"{DISK_ENTRY}.6.1": "Healthy",
        f"{DISK_ENTRY}.7.1": "42",
        f"{DISK_ENTRY}.2.2": "Disk1",
        f"{DISK_ENTRY}.6.2": "Normal",
        f"{DISK_ENTRY}.7.2": "47",
    }
    reordered = {
        f"{DISK_ENTRY}.{oid.split('.')[-2]}.{3 - int(oid.split('.')[-1])}": value for oid, value in first.items()
    }

    assert (
        _process_drive_data(first)
        == _process_drive_data(reordered)
        == {
            "disk0": {"name": "Disk0", "smart_status": "Healthy", "temperature": 42},
            "disk1": {"name": "Disk1", "smart_status": "Normal", "temperature": 47},
        }
    )


def test_missing_or_ambiguous_drive_readings_are_not_misattributed():
    assert _process_drive_data(
        {
            f"{DISK_ENTRY}.2.1": "Disk0",
            f"{DISK_ENTRY}.2.2": "Disk0",
            f"{DISK_ENTRY}.6.2": "Healthy",
            f"{DISK_ENTRY}.2.3": "Disk2",
            f"{DISK_ENTRY}.6.3": "Risky",
            f"{DISK_ENTRY}.7.3": "N/A",
            f"{DISK_ENTRY}.7.4": "41",
        }
    ) == {"disk2": {"name": "Disk2", "smart_status": "Risky", "temperature": None}}
