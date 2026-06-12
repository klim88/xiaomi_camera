# Xiaomi Camera for Home Assistant

Home Assistant custom integration that adds Xiaomi Mi Home cameras through go2rtc.

The integration uses the go2rtc Xiaomi module for account login, camera discovery and P2P video access. It then creates Home Assistant `camera` entities that can be used on dashboards, in automations and in other integrations that consume Home Assistant cameras.

## What It Does

- Logs in to Xiaomi Mi Home through the go2rtc API during setup.
- Loads Xiaomi camera devices from the selected account and region.
- Creates persistent go2rtc streams for the selected cameras.
- Adds Home Assistant `camera` entities with snapshots and RTSP stream sources.
- Stores no Xiaomi token in this repository.

## Requirements

Install and start go2rtc before adding this integration.

Recommended Home Assistant setup:

1. Add the go2rtc add-on repository:

```text
https://github.com/AlexxIT/hassio-addons
```

2. Install and start the `go2rtc` add-on.
3. Make sure the go2rtc Web/API port is reachable from Home Assistant.

Typical go2rtc API URL examples:

```text
http://127.0.0.1:1984
http://homeassistant.local:1984
http://ccab4aaf_go2rtc:1984
```

The matching RTSP base URL normally uses the same host with port `8554`:

```text
rtsp://127.0.0.1:8554
rtsp://homeassistant.local:8554
rtsp://ccab4aaf_go2rtc:8554
```

## HACS Install

1. Open HACS.
2. Open the three-dot menu.
3. Select `Custom repositories`.
4. Add repository:

```text
https://github.com/klim88/xiaomi_camera
```

5. Category: `Integration`.
6. Install `Xiaomi Camera`.
7. Restart Home Assistant.
8. Add the integration:

```text
Settings -> Devices & services -> Add integration -> Xiaomi Camera
```

Enter:

- go2rtc API URL;
- optional RTSP base URL;
- Xiaomi Mi Home login and password;
- Xiaomi region.

If go2rtc asks for a captcha or verification code, Home Assistant will show the next setup step.

## Camera Setup

After login, the integration asks which Xiaomi cameras to add. For every selected camera it creates a go2rtc stream with a generated local stream name and then adds a Home Assistant camera entity.

The integration does not require a hard-coded camera IP, `did`, MAC address or Xiaomi token in the repository.

## Security Notes

- Do not publish your `go2rtc.yaml`; it contains Xiaomi tokens after login.
- Do not publish Home Assistant `.storage` files; they contain config entry data.
- This repository only contains integration code and placeholder documentation.
- Examples intentionally use placeholder hostnames and do not include real camera IDs.

## Troubleshooting

If Home Assistant shows a camera but the stream does not play:

- confirm that go2rtc can open the camera in its own Web UI;
- confirm the RTSP base URL is reachable from Home Assistant;
- try using the go2rtc add-on hostname instead of `127.0.0.1` if Home Assistant runs in a different container;
- check that port `8554` is enabled for go2rtc.

If setup cannot find cameras:

- confirm that the selected Xiaomi region is the same region used in the Mi Home app;
- open go2rtc Web UI and test `Add -> Xiaomi` there;
- restart go2rtc after a successful Xiaomi login if the device list looks stale.
