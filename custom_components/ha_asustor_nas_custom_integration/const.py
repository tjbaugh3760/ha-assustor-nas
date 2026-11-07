"""Constants for ha_asustor_nas_custom_integration."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

# Integration metadata
DOMAIN = "ha_asustor_nas_custom_integration"

# Default configuration values
DEFAULT_PORT = 161
DEFAULT_COMMUNITY = "public"
DEFAULT_SCAN_INTERVAL = 300  # 5 minutes

CONF_COMMUNITY = "community"
CONF_SNMP_VERSION = "snmp_version"
CONF_AUTH_PROTOCOL = "auth_protocol"
SNMP_V2C = "2c"
SNMP_V3 = "3"

# Platform parallel updates - applied to all platforms
PARALLEL_UPDATES = 0  # 0 for async

# --- SNMP OIDs ---

# System / Network (IF-MIB)
OID_MAC_ADDRESS_BASE = "1.3.6.1.2.1.2.2.1.6"

# ASUSTOR Enterprise MIB (1.3.6.1.4.1.44738.2)
OID_ASUSTOR_MODEL = "1.3.6.1.4.1.44738.2.1.0"
OID_ASUSTOR_CPU_MODEL = "1.3.6.1.4.1.44738.2.2.0"

# Tables (Base OIDs for snmpwalk)
OID_ASUSTOR_CPU_CORE_USAGE_BASE = "1.3.6.1.4.1.44738.2.3.1.2"
OID_ASUSTOR_FAN_RPM_BASE = "1.3.6.1.4.1.44738.2.4.1.2"

# Temperatures (Single row table)
OID_ASUSTOR_TEMP_CPU = "1.3.6.1.4.1.44738.2.5.1.2.1"
OID_ASUSTOR_TEMP_SYS = "1.3.6.1.4.1.44738.2.5.1.3.1"

# Standard Linux Memory (UCD-SNMP-MIB)
OID_MEM_TOTAL = "1.3.6.1.4.1.2021.4.5.0"
OID_MEM_AVAIL = "1.3.6.1.4.1.2021.4.6.0"
OID_MEM_BUFFER = "1.3.6.1.4.1.2021.4.14.0"
OID_MEM_CACHED = "1.3.6.1.4.1.2021.4.15.0"

# Storage (HOST-RESOURCES-MIB)
OID_HR_STORAGE_TABLE_BASE = "1.3.6.1.2.1.25.2.3.1"
OID_HR_STORAGE_TYPE = "1.3.6.1.2.1.25.2.3.1.2"
OID_HR_STORAGE_DESCR = "1.3.6.1.2.1.25.2.3.1.3"
OID_HR_STORAGE_ALLOCATION_UNITS = "1.3.6.1.2.1.25.2.3.1.4"
OID_HR_STORAGE_SIZE = "1.3.6.1.2.1.25.2.3.1.5"
OID_HR_STORAGE_USED = "1.3.6.1.2.1.25.2.3.1.6"
OID_HR_STORAGE_FIXED_DISK = "1.3.6.1.2.1.25.2.1.4"

# File system table (HOST-RESOURCES-MIB)
OID_HR_FS_TABLE_BASE = "1.3.6.1.2.1.25.3.8.1"
OID_HR_FS_MOUNT_POINT = "1.3.6.1.2.1.25.3.8.1.2"
OID_HR_FS_STORAGE_INDEX = "1.3.6.1.2.1.25.3.8.1.7"
