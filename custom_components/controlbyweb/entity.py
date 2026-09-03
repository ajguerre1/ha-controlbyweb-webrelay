"""What every ControlByWeb entity shares.

All four relays are read in one request, so they succeed and fail together. There
is deliberately no per-relay availability here: unlike a device made of
independently polled components, this one either answered or it did not.
"""

from __future__ import annotations

from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_RELAY_NAME, CONF_RELAYS
from .coordinator import ControlByWebCoordinator


class ControlByWebEntity(CoordinatorEntity[ControlByWebCoordinator]):
    """An entity backed by one relay on the board."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ControlByWebCoordinator,
        relay: int,
        description: EntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._relay = relay
        self._attr_device_info = coordinator.device_info

        # Keyed on the config entry rather than anything the device reports,
        # because the device reports nothing identifying. `entry_id` is stable
        # across the address changes that `unique_id` is not.
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{relay}_{description.key}"

    @property
    def _relay_options(self) -> dict:
        """This relay's slice of the config entry options.

        Keys are strings because options round-trip through JSON, which has no
        integer keys -- looking one up with an int silently finds nothing.
        """
        relays = self.coordinator.config_entry.options.get(CONF_RELAYS, {})
        return relays.get(str(self._relay), {})

    @property
    def translation_placeholders(self) -> dict[str, str]:
        """Fill the entity name with this relay's configured label.

        Defaults to its number, so an unconfigured board reads as "Relay 1"
        rather than as a blank.
        """
        return {"relay": self._relay_options.get(CONF_RELAY_NAME) or str(self._relay)}

    @property
    def _is_closed(self) -> bool | None:
        """Whether this relay's coil is currently closed."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data[self._relay - 1]
