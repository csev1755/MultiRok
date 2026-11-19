CONFIG_SCHEMA = {
    "webserver": {
        "label": "Web Server",
        "type": "section",
        "options": {
            "listen_ip": {
                "type": "str",
                "default": "0.0.0.0",
                "label": "Listen IP",
                "description": "IP address the web server will listen on.",
            },
            "listen_port": {
                "type": "int",
                "default": 5001,
                "min": 1,
                "max": 65535,
                "label": "Listen Port",
                "description": "Port the web server will listen on.",
            },
            "enable_video": {
                "type": "bool",
                "default": False,
                "label": "Enable Video",
                "description": "Enables video streaming using go2rtc when enabled.",
            },
            "player_timeout": {
                "type": "int",
                "default": 30,
                "min": 1,
                "max": 600,
                "label": "Vehicle Timeout",
                "description": "Number of seconds before a player loses their selection if no inputs are made.",
            },
            "max_players": {
                "type": "int",
                "default": 12,
                "min": 1,
                "max": 100,
                "label": "Maximum Players",
                "description": "Maximum number of connected players.",
            },
            "max_player_name_length": {
                "type": "int",
                "default": 20,
                "min": 1,
                "max": 100,
                "label": "Maximum Player Name Length",
                "description": "Maximum number of characters allowed for player names.",
            },
            "allow_share": {
                "type": "bool",
                "default": False,
                "label": "Allow Share",
                "description": "Allows players to share vehicles when selected.",
            },
        },
    },
    "vehicle_types": {
        "label": "Vehicles",
        "type": "vehicle_dynamic_map",
        "description": "Configuration of all vehicle numbers, names, and types.  Vehicle numbers must start with 1 and count upwards consecutively.",
        "sources": {
            "smart_port_serial": {
                "label": "Smart Port Serial",
                "max_key": 15,
                "options": {
                    "serial_port": {
                        "type": "str",
                        "default": "auto",
                        "label": "Serial Port",
                        "description": "COM port, device path, or 'auto' for automatic port detection.",
                    },
                    "enable_wifi": {
                        "type": "bool",
                        "default": False,
                        "label": "Enable WiFi",
                        "description": "WiFi/webserver remain on when selected (for applicable device types).",
                    },
                },
            },
            "test_device": {
                "label": "Test Device",
                "max_key": None,
                "options": {
                    "test_option": {
                        "type": "bool",
                        "default": False,
                        "label": "Test Option",
                        "description": "Does absolutely nothing.",
                    },
                },
            },
        },
    },
    "video_streams": {
        "label": "Video Streams",
        "type": "dynamic_map",
        "key_range": (1, 20),
        "description": "Available go2rtc stream names and URLs.",
    },
    "logging": {
        "label": "Logging",
        "type": "section",
        "options": {
            "main": {
                "type": "choice",
                "choices": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                "default": "WARNING",
                "label": "Main Logging Level",
                "description": "Verbosity of the main application logging messages.",
            },
            "aiohttp": {
                "type": "choice",
                "choices": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                "default": "ERROR",
                "label": "AIOHTTP Logging Level",
                "description": "Verbosity of aiohttp server logging messages.",
            },
            "go2rtc": {
                "type": "choice",
                "choices": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                "default": "ERROR",
                "label": "go2rtc Logging Level",
                "description": "Verbosity of go2rtc application logging messsages.",
            },
            "file": {
                "type": "bool",
                "default": False,
                "label": "Enable Log File",
                "description": "The server will save all logs to a file when selected.",
            },
        },
    },
}
