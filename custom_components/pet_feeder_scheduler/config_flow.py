"""Config flow for Pet Feeder Scheduler.

There is nothing to configure. Adding the integration once from
Settings > Devices & services makes the set_schedule action available.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class PetFeederSchedulerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-step flow; manifest.json limits it to one entry."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm and create the entry."""
        if user_input is not None:
            return self.async_create_entry(title="Pet Feeder Scheduler", data={})
        return self.async_show_form(step_id="user")
