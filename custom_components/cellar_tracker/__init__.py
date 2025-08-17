"""Cellar Tracker integration for Home Assistant."""

from __future__ import annotations

import logging
from datetime import timedelta

import pandas as pd
import voluptuous as vol
from cellartracker import cellartracker
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType
import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle

_LOGGER = logging.getLogger(__name__)

DOMAIN = "cellar_tracker"

SCAN_INTERVAL = timedelta(hours=1)
MIN_TIME_BETWEEN_UPDATES = timedelta(hours=1)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Cellar Tracker integration."""
    conf = config[DOMAIN]

    username = conf[CONF_USERNAME]
    password = conf[CONF_PASSWORD]

    hass.data[DOMAIN] = WineCellarData(username, password)
    await hass.async_add_executor_job(hass.data[DOMAIN].update)

    # Load the sensor platform
    hass.async_create_task(
        async_load_platform(hass, "sensor", DOMAIN, {}, config)
    )

    return True


class WineCellarData:
    """Handle fetching and caching Cellar Tracker data."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._data: dict = {}

    def get_reading(self, key: str):
        return self._data.get(key)

    def get_readings(self):
        return self._data

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self, **kwargs):
        """Fetch data from CellarTracker."""
        data = {}
        username = self._username
        password = self._password

        client = cellartracker.CellarTracker(username, password)
        inventory = client.get_inventory()

        df = pd.DataFrame(inventory)
        df[["Price", "Valuation"]] = df[["Price", "Valuation"]].apply(pd.to_numeric)

        groups = ["Varietal", "Country", "Vintage", "Producer", "Type", "Location"]

        for group in groups:
            group_data = df.groupby(group).agg(
                {"iWine": "count", "Valuation": ["sum", "mean"]}
            )
            group_data.columns = group_data.columns.droplevel(0)
            group_data["%"] = (group_data["count"] / group_data["count"].sum()) * 100
            group_data.columns = ["count", "value_total", "value_avg", "%"]

            data[group] = {}
            for row, item in group_data.iterrows():
                if row == "1001":
                    row = "NV"
                data[group][row] = item.to_dict()
                data[group][row]["sub_type"] = row

        data["total_bottles"] = len(df)
        data["total_value"] = df["Valuation"].sum()
        data["average_value"] = df["Valuation"].mean()

        self._data = data
