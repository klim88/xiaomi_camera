from __future__ import annotations

from typing import Any

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CAMERAS, CONF_STREAM_NAME, DOMAIN
from .go2rtc import Go2RTCClient, camera_hash


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        XiaomiCameraEntity(client, entry, camera)
        for camera in entry.data.get(CONF_CAMERAS, [])
    )


class XiaomiCameraEntity(Camera):
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self,
        client: Go2RTCClient,
        entry: ConfigEntry,
        camera: dict[str, Any],
    ) -> None:
        super().__init__()
        self._client = client
        self._entry = entry
        self._camera = camera
        self._stream_name = camera[CONF_STREAM_NAME]
        self._attr_name = camera.get("name") or "Xiaomi Camera"
        self._attr_unique_id = f"{entry.entry_id}_{camera_hash(camera)}"

    async def async_camera_image(
        self,
        width: int | None = None,
        height: int | None = None,
    ) -> bytes | None:
        return await self._client.async_camera_image(self._stream_name)

    async def stream_source(self) -> str | None:
        return self._client.rtsp_stream_url(self._stream_name)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "go2rtc_stream": self._stream_name,
            "model": self._camera.get("model") or None,
        }

    @property
    def device_info(self):
        model = self._camera.get("model") or "Mi Home camera"
        return {
            "identifiers": {(DOMAIN, camera_hash(self._camera))},
            "manufacturer": "Xiaomi",
            "name": self._camera.get("name") or "Xiaomi Camera",
            "model": model,
        }
