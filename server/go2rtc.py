import os
import platform
import re
import time
import subprocess
import requests
import yaml
from urllib import parse


class Go2RTC:
    """
    Manages the go2rtc streamer as a subprocess
    """

    def __init__(self, bundle_dir, config, log_level, logger):
        self.logger = logger
        self.proc = None

        self.bin = os.path.join(bundle_dir, "bin", "go2rtc")
        self.config = os.path.join(bundle_dir, "bin", "go2rtc.yaml")
        self.ffmpeg = os.path.join(bundle_dir, "bin", "ffmpeg.bin")

        # Get video stream config from settings.ini
        streams = {stream: device for stream, device in config.items("video_streams") if device}

        # Construct go2rtc config
        self.go2rtc_config = {
            "ffmpeg": {
                "bin": self.ffmpeg,
                "mjpeg": '-c:v mjpeg -q:v 2 -vf "unsharp=5:5:0.5:5:5:0.0"',
            },
            "webrtc": {"listen": ":8555", "candidates": ["stun:8555"]},
            "streams": streams,
            "log": {"format": "text", "level": log_level},
        }

    def get_devices(self, url):
        """
        Retrieves and transforms video device URLs

        Returns:
            list: A list of dictionaries containing device information (name, url, source_url)
        """

        def get_avfoundation_devices():
            # Use ffmpeg to list AVFoundation devices
            process = subprocess.Popen(
                [self.ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "avfoundation", "-i", "dummy"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            stdout, stderr = process.communicate()
            raw_output = stderr if stderr else stdout
            devices = []
            device_line_pattern = re.compile(r"^\[AVFoundation[^\]]*\]\s*\[\d+\]\s+(.*)")

            for line in raw_output.splitlines():
                # Filter out audio devices
                if "AVFoundation audio devices:" in line:
                    break

                match = device_line_pattern.search(line)
                if not match:
                    continue

                rest = match.group(1)

                # Look for AVFoundation device unique IDs
                serial_match = re.search(r"\[serial:([^\]]+)\]", rest)
                uid_match = re.search(r"\[uid:([^\]]+)\]", rest)
                serial = serial_match.group(1) if serial_match else None
                uid = uid_match.group(1) if uid_match else None

                rest = re.sub(r"\[(?:uid|serial):[^\]]+\]", "", rest)
                name = rest.strip()

                # Prefer serial or UID for device identification
                if serial:
                    device_id = f"serial:{serial}"
                elif uid:
                    device_id = f"uid:{uid}"
                else:
                    device_id = None

                if device_id:
                    device_url = f"ffmpeg:device?video_device_id={device_id}"
                else:
                    device_url = f"ffmpeg:device?video={name}"

                devices.append(
                    {
                        "name": name,
                        "url": device_url,
                        "source_url": device_url,
                    }
                )

            return devices

        def get_dshow_devices():
            # Use the go2rtc API to list DirectShow devices
            response = requests.get(url)
            data = response.json()
            devices = []
            for source in data.get("sources", []):
                url_str = source.get("url", "")

                # Skip sources that are missing a URL string
                if not url_str:
                    continue

                # Filter for video devices
                parsed_url = parse.urlparse(url_str)
                query_params = parse.parse_qs(parsed_url.query)
                if "video" not in query_params:
                    continue

                # Remove #hardware from the URL string to disable hardware acceleration
                fragment_parts = parsed_url.fragment.split("#")
                clean_fragment = "#".join(part for part in fragment_parts if "hardware" not in part)
                modified_url = parse.urlunparse(parsed_url._replace(fragment=clean_fragment))

                devices.append(
                    {
                        "name": source["name"],
                        "url": modified_url,
                        "source_url": url_str,
                    }
                )

            return devices

        if platform.system() == "Darwin":
            return get_avfoundation_devices()
        return get_dshow_devices()

    def start(self):
        with open(self.config, "w") as f:
            yaml.dump(self.go2rtc_config, f, default_flow_style=False, sort_keys=False)

        self.proc = subprocess.Popen([self.bin, "-c", self.config])

        for _ in range(10):
            try:
                devices = self.get_devices("http://127.0.0.1:1984/api/ffmpeg/devices")
                for device in devices:
                    print(f" * Found go2rtc video device - {device['name']} - {device['url']}")
                return
            except Exception:
                time.sleep(0.2)

    def stop(self):
        if self.proc:
            print("Stopping go2rtc...")
            self.proc.terminate()
