import logging
from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

"""
Configures Ksenia sensors in Home Assistant.

Retrieves a list of sensors from the WebSocket manager, creates a `KseniaSensorEntity` for each sensor,
and adds them to the system.

Args:
    hass: The Home Assistant instance.
    config_entry: The configuration entry for the Ksenia sensors.
    async_add_entities: A callback to add entities to the system.
"""
async def async_setup_entry(hass, config_entry, async_add_entities):
    ws_manager = hass.data[DOMAIN]["ws_manager"]
    entities = []

    # DOMUS sensors
    domus = await ws_manager.getDom()
    _LOGGER.debug("Received domus data: %s", domus)
    for sensor in domus:
        entities.append(KseniaSensorEntity(ws_manager, sensor, "domus"))

    # POWERLINES sensors
    powerlines = await ws_manager.getSensor("POWER_LINES")
    _LOGGER.debug("Received powerlines data: %s", powerlines)
    for sensor in powerlines:
        entities.append(KseniaSensorEntity(ws_manager, sensor, "powerlines"))

    # PARTITIONS sensors
    partitions = await ws_manager.getSensor("PARTITIONS")
    _LOGGER.debug("Received partitions data: %s", partitions)
    for sensor in partitions:
        entities.append(KseniaSensorEntity(ws_manager, sensor, "partitions"))

    # ZONES sensors
    zones = await ws_manager.getSensor("ZONES")
    _LOGGER.debug("Received zones data: %s", zones)
    for sensor in zones:
        entities.append(KseniaSensorEntity(ws_manager, sensor, "zones"))

    # SYSTEM sensors for system status
    systems = await ws_manager.getSystem()
    _LOGGER.debug("Received systems data: %s", systems)
    for sensor in systems:
        entities.append(KseniaSensorEntity(ws_manager, sensor, "system"))

    async_add_entities(entities, update_before_add=True)

class KseniaSensorEntity(SensorEntity):

    """
    Initializes a Ksenia sensor entity.

    :param ws_manager: WebSocketManager instance to command Ksenia
    :param sensor_data: Dictionary with the sensor data
    :param sensor_type: Type of the sensor (domus, powerlines, partitions, zones, system)
    """
    def __init__(self, ws_manager, sensor_data, sensor_type):
        self.ws_manager = ws_manager
        self._id = sensor_data["ID"]
        self._sensor_type = sensor_type
        self._name = sensor_data.get("NM") or sensor_data.get("LBL") or sensor_data.get("DES") or f"Sensor {sensor_type.capitalize()} {self._id}"

        if sensor_type == "system":
            # Extract temperature from sensor data
            temp_data = sensor_data.get("TEMP", {})
            try:
                temp_in = float(temp_data.get("IN", "0").replace("+", "")) if temp_data.get("IN") else None
                temp_out = float(temp_data.get("OUT", "0").replace("+", "")) if temp_data.get("OUT") else None
            except Exception as e:
                _LOGGER.error("Error converting temperature: %s", e)
                temp_in = None
                temp_out = None
            self._state = sensor_data.get("ARM", "unknown")
            self._attributes = {"temp_in": temp_in, "temp_out": temp_out}

        elif sensor_type == "powerlines":
            # Extract consumption and production
            pcons = sensor_data.get("PCONS")
            try:
                pcons_val = float(pcons) if pcons and pcons.replace('.', '', 1).isdigit() else None
            except Exception as e:
                _LOGGER.error("Error converting PCONS: %s", e)
                pcons_val = None
            pprod = sensor_data.get("PPROD")
            try:
                pprod_val = float(pprod) if pprod and pprod.replace('.', '', 1).isdigit() else None
            except Exception as e:
                _LOGGER.error("Error converting PPROD: %s", e)
                pprod_val = None
            # Use PCONS if it exists, otherwise use STATUS
            self._state = pcons_val if pcons_val is not None else sensor_data.get("STATUS", "unknown")
            self._attributes = {
                "Consumo": pcons_val,
                "Produzione": pprod_val,
                "Status": sensor_data.get("STATUS", "unknown")
            }

        elif sensor_type == "domus":
            # Manage domus sensors, extract temperature and humidity
            try:
                temperature = float(sensor_data.get("T", "0").replace("+", "")) if sensor_data.get("T") else None
            except Exception as e:
                _LOGGER.error("Error converting temperature in domus sensor: %s", e)
                temperature = None
            try:
                humidity = float(sensor_data.get("H", "0")) if sensor_data.get("H") else None
            except Exception as e:
                _LOGGER.error("Error converting humidity in domus sensor: %s", e)
                humidity = None
            self._state = temperature if temperature is not None else sensor_data.get("STA", "unknown")
            self._attributes = {**sensor_data, "temperature": temperature, "humidity": humidity}

        elif sensor_type == "partitions":
            # Manage partitions sensors, extract total consumption
            total_consumption = 0.0
            stat = sensor_data.get("STAT", [])
            if stat:
                latest_stat = stat[-1]
                vals = latest_stat.get("VAL", [])
                for record in vals:
                    try:
                        total_consumption += float(record.get("ENC", 0))
                    except Exception as e:
                        _LOGGER.error("Error converting total consumption: %s", e)
            self._state = total_consumption if total_consumption > 0 else sensor_data.get("STA", "unknown")
            self._attributes = {**sensor_data, "total_consumption": total_consumption}

        else:
            self._state = sensor_data.get("STA", "unknown")
            self._attributes = sensor_data


    @property
    def unique_id(self):
        """Returns a unique ID for the sensor."""
        return f"{self._sensor_type}_{self._id}"

    @property
    def name(self):
        """Returns the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Returns the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Returns the extra state attributes of the sensor."""
        return self._attributes


    """
    Update the state of the sensor.
    
    This method is called periodically by Home Assistant to refresh the sensor's state.
    It retrieves the latest data from the Ksenia system and updates the sensor's state
    and attributes accordingly.
    """
    async def async_update(self):
        if self._sensor_type == "system":
            systems = await self.ws_manager.getSystem()
            for sys in systems:
                if sys["ID"] == self._id:
                    temp_data = sys.get("TEMP", {})
                    try:
                        temp_in = float(temp_data.get("IN", "0").replace("+", "")) if temp_data.get("IN") else None
                        temp_out = float(temp_data.get("OUT", "0").replace("+", "")) if temp_data.get("OUT") else None
                    except Exception as e:
                        _LOGGER.error("Error converting temperature: %s", e)
                        temp_in = None
                        temp_out = None
                    self._state = sys.get("ARM", "unknown")
                    self._attributes = {"temp_in": temp_in, "temp_out": temp_out}
                    break

        elif self._sensor_type == "powerlines":
            sensors = await self.ws_manager.getSensor("POWER_LINES")
            for sensor in sensors:
                if sensor["ID"] == self._id:
                    pcons = sensor.get("PCONS")
                    try:
                        pcons_val = float(pcons) if pcons and pcons.replace('.', '', 1).isdigit() else None
                    except Exception as e:
                        _LOGGER.error("Error converting PCONS: %s", e)
                        pcons_val = None
                    pprod = sensor.get("PPROD")
                    try:
                        pprod_val = float(pprod) if pprod and pprod.replace('.', '', 1).isdigit() else None
                    except Exception as e:
                        _LOGGER.error("Error converting PPROD: %s", e)
                        pprod_val = None
                    self._state = pcons_val if pcons_val is not None else sensor.get("STATUS", "unknown")
                    self._attributes = {
                        "Consumo": pcons_val,
                        "Produzione": pprod_val,
                        "Status": sensor.get("STATUS", "unknown")
                    }
                    break

        elif self._sensor_type == "domus":
            sensors = await self.ws_manager.getDom()
            for sensor in sensors:
                if sensor["ID"] == self._id:
                    try:
                        temperature = float(sensor.get("T", "0").replace("+", "")) if sensor.get("T") else None
                    except Exception as e:
                        _LOGGER.error("Error converting temperature in domus sensor update: %s", e)
                        temperature = None
                    try:
                        humidity = float(sensor.get("H", "0")) if sensor.get("H") else None
                    except Exception as e:
                        _LOGGER.error("Error converting humidity in domus sensor update: %s", e)
                        humidity = None
                    self._state = temperature if temperature is not None else sensor.get("STA", "unknown")
                    self._attributes = {**sensor, "temperature": temperature, "humidity": humidity}
                    break

        elif self._sensor_type == "partitions":
            sensors = await self.ws_manager.getSensor("PARTITIONS")
            for sensor in sensors:
                if sensor["ID"] == self._id:
                    total_consumption = 0.0
                    stat = sensor.get("STAT", [])
                    if stat:
                        latest_stat = stat[-1]
                        vals = latest_stat.get("VAL", [])
                        for record in vals:
                            try:
                                total_consumption += float(record.get("ENC", 0))
                            except Exception as e:
                                _LOGGER.error("Error converting ENC in partitions sensor update: %s", e)
                    self._state = total_consumption if total_consumption > 0 else sensor.get("STA", "unknown")
                    self._attributes = {**sensor, "total_consumption": total_consumption}
                    break

        else:
            # For other sensors, we need to call getSensor with the specific type
            sensors = await self.ws_manager.getSensor(self._sensor_type.upper())
            for sensor in sensors:
                if sensor["ID"] == self._id:
                    self._state = sensor.get("STA", "unknown")
                    self._attributes = sensor
                    break