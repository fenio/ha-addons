# Add-ons for Home Assistant

[![License](https://img.shields.io/github/license/fenio/ha-unbound-addon.svg)](LICENSE)

Home Assistant add-ons repository.

## Add-ons

### [Omada Controller (No AVX)](./omada-controller-no-avx)

![Version](https://img.shields.io/badge/version-6.0.0.25--b8-blue.svg)

TP-Link Omada Controller for CPUs without AVX support. The standard Omada Controller v6.x uses MongoDB which requires AVX CPU instructions, making it incompatible with older/low-power CPUs (Intel Atom, Celeron, older AMD, etc.). This add-on uses a custom-built MongoDB 7.0 without AVX requirements.

### [Unbound DNS](./unbound)

![Version](https://img.shields.io/badge/version-0.0.6-blue.svg)

A recursive DNS resolver using Unbound with support for:
- Local DNS records
- DNSSEC validation
- Caching with configurable TTL
- Forwarding or full recursive mode

## Installation

1. Click the button below to add this repository:

   [![Add repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https://github.com/fenio/ha-unbound-addon)

2. Or manually add the repository URL in Home Assistant:
   - Go to **Settings** > **Add-ons** > **Add-on Store**
   - Click **⋮** (three dots) > **Repositories**
   - Add: `https://github.com/fenio/ha-addons`
   - Click **Add** and **Close**

3. Refresh the add-on store and find add-on to install

## License

MIT License
