# Home Assistant ASUSTOR NAS Custom Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/NdR91/ha-assustor-nas.svg)](https://github.com/NdR91/ha-assustor-nas/releases)
[![License](https://img.shields.io/github/license/NdR91/ha-assustor-nas.svg)](LICENSE)

## 👋🏻 A Personal Note on This Integration

I am a technology enthusiast working as a Sales Engineer in an Italian tech company, with a strong focus on Generative AI. I do not come from a traditional software development background, so building this integration was a real challenge from day one.

The idea was simple: create a practical and reliable way to monitor ASUSTOR NAS devices in Home Assistant without complex YAML setups or fragile reverse-engineered APIs.

With patience, many iterations, and AI-assisted development, this project gradually became stable enough for daily use.

👉 **This integration is developed with substantial AI support.**

Because of that, some parts may still look unconventional. Feedback, reviews, and pull requests are always welcome: this project improves release after release with community input.

This is an open and evolving project.

> This project is an independent community integration and is not affiliated with or endorsed by ASUSTOR Inc.

---

## 🌟 Features

This integration monitors your ASUSTOR NAS from Home Assistant over SNMPv3 or SNMPv2c.

On NAS models that expose the ASUSTOR disk table, the integration creates SMART status and temperature sensors for each drive. It uses the disk ID reported by ADM to keep the sensor identity stable if the SNMP row index changes.

- **UI Configuration**: No YAML required. Set up everything through the Home Assistant Config Flow.
- **Dynamic Discovery**: Automatically detects and creates sensors for:
  - Every CPU Core (Usage %)
  - Every Fan (RPM)
  - Every Temperature Sensor (CPU, System/Motherboard)
  - NAS Volumes exposed as root mounts (`/volumeN`) with Total/Used/Free/Usage
- **Accurate Memory Calculation**: Calculates real memory usage (Total - Free - Buffers - Cache) to match the ADM Activity Monitor UI, rather than relying on raw SNMP "Free" memory which is often misleading on Linux systems.
- **Memory Metrics**: Exposes Total/Used memory as Home Assistant data-size sensors and memory usage percentage.
- **Centralized Polling**: Uses Home Assistant's `DataUpdateCoordinator` to fetch all data in a single, efficient asynchronous cycle, preventing network spam and timeouts.

## 📊 Exposed Sensors

The integration exposes a mix of static and dynamic sensors.

### Static Sensors
- `Model`
- `CPU Model`
- `Total Memory`
- `Used Memory`
- `Memory Usage`

### Dynamic Sensors
- `CPU Core <n> Usage`
- `Fan <n>`
- `CPU Temperature`
- `System Temperature`

### Volume Sensors (per discovered root volume)
For each detected root volume (for example `volume1`, `volume2`), the integration creates:
- `<volume> Total`
- `<volume> Used`
- `<volume> Free`
- `<volume> Usage`

Notes:
- Volume sensors are discovered from `HOST-RESOURCES-MIB` and mapped through filesystem mount points.
- The integration includes root mounts like `/volume1`, `/volume2` and excludes technical mounts to avoid duplicates/noise.

## 🛠️ Prerequisites

Before installing this integration, you must enable SNMP on your ASUSTOR NAS:

1. Log in to your ASUSTOR ADM interface.
2. Go to **Settings** > **Services** > **SNMP**.
3. Enable the SNMP service.
4. For SNMPv3, enable **SNMP V3 service** and create a dedicated SNMP username and password. SNMPv3 uses authentication without encryption (`authNoPriv`). MD5 is the default and was verified on the AS5304T. Choose SHA-1 only if your NAS uses it.
5. For an existing SNMPv2c installation, use the community string configured in ADM.

## 📦 Installation

### Method 1: Marketplace (Recommended)

**Home Assistant 2026.11 and later:** open **Settings > Marketplace**, choose **Add from link**, and enter `https://github.com/NdR91/ha-assustor-nas`. Follow the prompts to install the integration, then restart Home Assistant.

**Earlier Home Assistant versions:** install through HACS. Open **HACS > Integrations > ⋮ > Custom repositories**, add `https://github.com/NdR91/ha-assustor-nas` with category **Integration**, then find **ASUSTOR NAS** in HACS and download it. Restart Home Assistant.

### Method 2: Manual

1. Download the latest release from this repository.
2. Extract the `custom_components/ha_asustor_nas_custom_integration` folder.
3. Copy it into your Home Assistant `custom_components` directory.
4. Restart Home Assistant.

## ⚙️ Configuration

1. In Home Assistant, go to **Settings** > **Devices & Services**.
2. Click **Add Integration** in the bottom right corner.
3. Search for **ASUSTOR NAS**.
4. Choose **SNMPv3** or **SNMPv2c** and enter the required information:
   - **Host**: The IP address or hostname of your NAS.
   - **Port**: The SNMP port (default is `161`).
   - **SNMPv3**: Enter the username, authentication password, and authentication protocol configured in ADM.
   - **SNMPv2c**: Enter the community string configured in ADM.
   - **Scan Interval**: How often to poll the NAS for data (default is `300` seconds).
5. Click **Submit**.

## Volume sensors and upgrades

Volume sensors use the NAS mount point (for example, `/volume1`) as their identity. This keeps their Home Assistant entity identity stable if the SNMP table row number changes.

When a volume has multiple possible legacy entity matches, choose the correct entity in the integration options for each ambiguous metric. The integration does not automatically delete entity registry entries, and it does not merge the history of duplicate entities.

## 🏗️ Architecture & Technical Decisions

This integration was built following strict Home Assistant Core standards:

- **SNMP polling** uses the same connection settings for setup and regular polling. Existing entries without a protocol setting continue to use SNMPv2c.
- **Why `pysnmp` 7.x?** Home Assistant strictly forbids blocking I/O in the main event loop. `pysnmp` 7.x is the maintained upstream package and supports modern asyncio APIs used by this integration.
- **Unique ID Strategy**: ASUSTOR NAS devices do not expose a Serial Number via the standard `ENTITY-MIB`. To ensure a stable `unique_id` (so Home Assistant recognizes the device even if its IP changes), the integration fetches the MAC address of the first network interface via `IF-MIB`.
- **Memory Calculation**: The ASUSTOR Enterprise MIB only exposes "Free" memory. On Linux, this value is almost zero because unused RAM is used for caching. To provide a "Memory Usage" percentage that matches the ADM web UI, we use the standard Linux `UCD-SNMP-MIB` to calculate: `Total - (Free + Buffers + Cache)`.

## 🤝 Contributing

Contributions are welcome! If you find a bug or have a feature request, please open an issue. If you want to contribute code, feel free to open a pull request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
