from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "xiaomi_camera"
PLATFORMS = [Platform.CAMERA]

CONF_ACCOUNT_ID = "account_id"
CONF_CAMERAS = "cameras"
CONF_GO2RTC_RTSP_URL = "go2rtc_rtsp_url"
CONF_GO2RTC_URL = "go2rtc_url"
CONF_REGION = "region"
CONF_SELECTED_CAMERAS = "selected_cameras"
CONF_STREAM_NAME = "stream_name"
CONF_STREAM_URL = "stream_url"

DEFAULT_GO2RTC_URL = "http://a889bffc-go2rtc:1984"

REGIONS = {
    "cn": "China",
    "de": "Europe",
    "i2": "India",
    "ru": "Russia",
    "sg": "Singapore",
    "us": "United States",
}
