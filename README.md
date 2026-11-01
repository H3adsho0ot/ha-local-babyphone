# Philips Avent SCD923/26 Baby Monitor for Home Assistant

> [!IMPORTANT]
> **Pairing key guide coming soon.** Setup requires the 16-byte local pairing key for your baby unit. A guide to extracting the key from your own device will be published here soon.

**Avent local** connects Home Assistant directly to your Philips Avent SCD923/26 over your home network. The dashboard card shows live video, room audio, temperature and Wi-Fi reception, with controls for talkback, the night light and lullabies.

**No Tuya Cloud or internet connection is required for local use.** Once the integration and its dependencies are installed, Home Assistant communicates with the baby unit over the LAN, and you can open the dashboard from a browser or phone on the same network. HACS needs internet access to download the integration and its updates from GitHub.

> [!WARNING]
> **Use the Home Assistant live view and the original parent unit in turn.** When both try to use the camera at the same time, they can compete for the connection and the live picture or audio can drop. Before switching back to the handheld, close **all** Home Assistant live views and wait about **10 seconds** for the integration to release the camera. If a browser or phone disconnected abruptly, allow extra time for the lost session to be detected. Check that the handheld has live picture and sound before relying on it.

## Install with HACS

[![Open Avent local in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=H3adsho0ot&repository=ha-local-babyphone&category=integration)

1. With [HACS](https://www.hacs.xyz/docs/use/download/download/) installed, use the button above to open **Avent local** in HACS and select **Download**. For manual registration, open **HACS → ⋮ → Custom repositories**, add `https://github.com/H3adsho0ot/ha-local-babyphone` and choose **Integration**.
2. Restart Home Assistant.
3. Under **Settings → Devices & services → Add integration**, select **Avent local**.
4. Enter the baby unit's LAN IP address or hostname and its **16-byte local pairing key**. The form accepts 16 ASCII characters or `hex:` followed by 32 hexadecimal digits. Keep this key private, including when filing issues.
5. Reload the dashboard or reopen the Companion App. Add the **Avent local** card, then select the camera entity created during setup. The integration registers the card automatically.

For a manual installation, copy `custom_components/local_babyphone` from the [release](https://github.com/H3adsho0ot/ha-local-babyphone/releases) into your Home Assistant `config/custom_components/` directory. Continue at step 2.

## Using the card

Open the card to start a live view. Several Home Assistant viewers share the same native camera connection. After the last viewer leaves, the integration releases the connection. Camera-derived sensors and local sound detection are available while the session is active.

| Control | What it does |
| --- | --- |
| Speaker and microphone | Listening starts muted. Tap the speaker to listen or the microphone to talk. Browser microphone access requires HTTPS or localhost and microphone permission. Simultaneous room audio during talkback is unverified. |
| Zoom and snapshot | Choose 1×, 2× or 4×. Drag the zoomed image or use the arrow keys. Home centers it. The card remembers the zoom and position for each HA user and camera on that browser or app. Save a snapshot from a live picture. |
| Night light and sounds | Tap to toggle. Hold the icon for brightness, a sound selection or a timer. |
| Temperature and sound detection | Set temperature limits or adjust local sound detection. The LED column shows the incoming audio level. Recent events appear in the card. |

English and German are included. The card follows the viewer's Home Assistant language and falls back to English. Media-player titles follow the HA server language.

## Compatibility and connection limits

- Version **0.5.2** was tested with an **SCD923/26** and **Home Assistant 2026.10.2**. Compatibility with other models and firmware versions is unverified.
- Home Assistant needs LAN access to the baby unit on TCP ports 554, 6000, 8684, 8686 and 8687. Start with a browser on the same network. The card uses WebRTC with local ICE candidates.
- Optional address discovery broadcasts the baby unit's direct Wi-Fi SSID on UDP port 6100 when a connection is needed. This exposes the SSID to devices on the broadcast network. Automatic recovery after an IP change has yet to be verified on hardware. If discovery fails, configure the current LAN address.
- **Privacy mode can disconnect the baby unit from the LAN.** The privacy switch is exposed as an HA entity. Keep the paired handheld available to turn privacy off if remote access is lost.

## Legal notice and safety

Avent local is an independent community interoperability project. It is not affiliated with, endorsed by or supported by Philips, Avent or the Home Assistant project. Product names and trademarks belong to their respective owners and are used to identify compatible equipment.

Use the integration only with equipment and networks you own or have permission to access. Follow the manufacturer's instructions. Video, audio and alerts can be delayed, interrupted or unavailable. Do not rely on this integration as the sole means of monitoring a child or for safety-critical alerts.

Project code is provided under the [MIT License](LICENSE), as is and without warranty, to the extent permitted by applicable law. The bundled aiortc code retains its [BSD license and copyright notices](custom_components/local_babyphone/vendor/aiortc/LICENSE). No rights to third-party trademarks or firmware are granted by this release.
