import os
import re
import subprocess
import requests
from pathlib import Path
from urllib.parse import urlparse
from core.models import StreamProfile
from apps.plugins.models import PluginConfig
from django.db import transaction
from typing import Dict, Any

class Plugin:
    name = "Dispatchwrapparr Plugin"
    version = "1.0.0"
    description = "An installer/updater and stream profile generator for Dispatchwrapparr"

    dw_path = "/data/dispatchwrapparr/dispatchwrapparr.py"
    dw_latest = "https://raw.githubusercontent.com/jordandalley/dispatchwrapparr/refs/heads/main/VERSION"
    dw_url = "https://raw.githubusercontent.com/jordandalley/dispatchwrapparr/refs/heads/main/dispatchwrapparr.py"
    base_dir = Path(__file__).resolve().parent
    plugin_key = base_dir.name.replace(" ", "_").lower()

    def __init__(self):
        try:
            self.context = PluginConfig.objects.get(key=self.plugin_key)
            self.settings = self.context.settings
        except PluginConfig.DoesNotExist:
            self.context = None
            if os.path.isfile(self.dw_path):
                self.settings = {"local_version": self.check_local_version()}
            else:
                self.settings = {}
                
        if os.path.isfile(self.dw_path) is False or self.settings.get("local_version") is None:
            self.actions = [
                {"id": "install", "label": "Install Dispatchwrapparr", "description": "Click 'Run' to install Dispatchwrapparr, then click the refresh icon in the top right corner."}
            ]
            
        else:
            self.fields = [
                {
                    "id": "profile_name",
                    "label": "Profile Name *",
                    "type": "string",
                    "default": "",
                    "help_text": "Mandatory: Enter a name for your stream profile",
                },
                {
                    "id": "loglevel", "label": "Logging Level", "type": "select", "default": "INFO",
                     "options": [
                         {"value": "INFO", "label": "INFO"},
                         {"value": "CRITICAL", "label": "CRITICAL"},
                         {"value": "ERROR", "label": "ERROR"},
                         {"value": "WARNING", "label": "WARNING"},
                         {"value": "DEBUG", "label": "DEBUG"},
                         {"value": "NOTSET", "label": "NOTSET"},
                    ]
                },
                {
                    "id": "proxy",
                    "label": "Proxy Server",
                    "type": "string",
                    "default": "",
                    "help_text": "Optional: Use an http proxy server for streams in this profile | Default: leave blank | Eg: 'http://proxy.address:8080'",
                },
                {
                    "id": "proxybypass",
                    "label": "Proxy Bypass",
                    "type": "string",
                    "default": "",
                    "help_text": "Optional: If using an http proxy server, enter a comma-delimited list of hostnames to bypass | Default: leave blank | Eg: '.example.com,.example.local:8080,192.168.0.2'",
                },
                {
                    "id": "clearkeys",
                    "label": "Clearkeys JSON file/URL",
                    "type": "string",
                    "default": "",
                    "help_text": "Optional: Specify a json file or URL that can be used to match DRM clearkeys to URL's (See Dispatchwrapparr documentation) | Default: leave blank | Eg: 'clearkeys.json' or 'https://path.to.clearkeys.api/clearkeys.json'",
                },
                {
                    "id": "cookies",
                    "label": "Cookies TXT file",
                    "type": "string",
                    "default": "",
                    "help_text": "Optional: Specify a cookies.txt file in Mozilla format containing session information for streams | Default: leave blank | Eg: 'cookies.txt'",
                },
                {
                    "id": "subtitles",
                    "label": "Enable Subtitles when Muxing",
                    "type": "boolean",
                    "default": False,
                    "help_text": "Optional: When muxing, include subtitles",
                }
            ]
            confirm_install = {
                "required": True,
                "title": "Install Dispatchwrapparr?",
                "message": "After installation is complete, click the refresh icon on the top right corner of this page",
            }
            confirm_update = {
                "required": True,
                "title": "Check for Updates?",
                "message": "This will check for available updates, and install them if available",
            }
            confirm_profile = {
                "required": True,
                "title": "Create stream profile?",
                "message": "This will create a new Dispatchwrapparr stream profile. After creation, please refresh the page and go to 'Settings' -> 'Stream Profiles' to view",
            }
            confirm_reset = {
                "required": True,
                "title": "Reset plugin?",
                "message": "This will reset the stream profile builder to default. Once complete, click the refresh icon on the top right corner of this page",
            }
            confirm_uninstall = {
                "required": True,
                "title": "Uninstall Dispatchwrapparr?",
                "message": "After uninstallation, you can then delete this plugin. You will need to manually remove any Dispatchwrapparr stream profiles from 'Settings' -> 'Stream Profiles'",
            }
            self.actions = [
                {"id": "create_profile", "label": "Create Stream Profile", "description": "Create a Dispatchwrapparr stream profile using the current settings", "confirm": confirm_profile},
                {"id": "reset_plugin", "label": "Reset Profile Builder", "description": "Restore default settings for the profile builder", "confirm": confirm_reset},
                {"id": "check_updates", "label": "Check for Updates", "description": f"Installed Version: v{self.settings.get('local_version')}", "confirm": confirm_update},
                {"id": "uninstall", "label": "Uninstall Dispatchwrapparr", "description": "Uninstall Dispatchwrapparr and reset plugin to defaults", "confirm": confirm_uninstall}
            ]

    # Validation functions
    def is_valid_url(self, url: str) -> bool:
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False

    def is_valid_proxy_bypass(self, value: str) -> bool:
        # Checks for compatible formats for env var NO_PROXY format
        noproxy_regex = re.compile(
            r'^(\.?[A-Za-z0-9.-]+(:\d+)?|\d{1,3}(\.\d{1,3}){3}(:\d+)?)$'
        )
        if not value:
            return True  # empty is valid (no bypass)

        parts = [v.strip() for v in value.split(",") if v.strip()]
        for part in parts:
            if not noproxy_regex.match(part):
                return False
        return True

    # Versioning functions
    def check_local_version(self):
        if os.path.isfile(self.dw_path):
            try:
                result = subprocess.run(
                    ["python3", self.dw_path, "-v"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                tokens = result.stdout.strip().split()
                if len(tokens) >= 2:
                    return tokens[1].strip()
                else:
                    return None
            except subprocess.CalledProcessError:
                return None
        else:
            return None

    def check_remote_version(self):
        resp = requests.get(self.dw_latest)
        resp.raise_for_status()
        version = resp.text.strip()
        return version

    # Handles installation and updates
    def install(self):
        path = os.path.dirname(self.dw_path)
        os.makedirs(path, exist_ok=True)
        resp = requests.get(self.dw_url)
        resp.raise_for_status()
        with open(self.dw_path, "w", encoding="utf-8") as f:
            f.write(resp.text)
        self.persist_settings({"local_version": self.check_local_version()})
        return {"status": "ok", "message": f"Installed Dispatchwrapparr v{self.settings.get('local_version')} to {self.dw_path}"}

    def check_updates(self):
        local_version = self.check_local_version()
        remote_version = self.check_remote_version()
        if local_version == remote_version:
            return {"status": "ok", "message": "Dispatchwrapparr is already up to date"}
        else:
            resp = requests.get(self.dw_url)
            resp.raise_for_status()
            with open(self.dw_path, "w", encoding="utf-8") as f:
                f.write(resp.text)
            self.persist_settings({"local_version": self.check_local_version()})
            return {"status": "ok", "message": f"Updated Dispatchwrapparr from v{local_version} to v{remote_version}"}

    # Handles stream profile creation and form validation
    def create_profile(self):
        if (self.settings.get("profile_name") or None) is None:
            return {"status": "error", "message": "Please specify a profile name!"}
        path = os.path.dirname(self.dw_path)
        profile_name = self.settings.get("profile_name").strip()
        if StreamProfile.objects.filter(name__iexact=profile_name).first():
            return {"status": "error", "message": f"Profile '{profile_name}' already exists!"}

        parameters = [
            "-ua", "{userAgent}",
            "-i", "{streamUrl}",
            "-loglevel", (self.settings.get("loglevel") or "INFO").strip()
        ]
        # Validate and set proxy settings
        proxy = (self.settings.get("proxy") or "").strip()
        if proxy:
            if self.is_valid_url(proxy) is False:
                return {"status": "error", "message": f"Proxy Server: '{proxy}' is not a valid proxy server!"}
            parameters += ["-proxy", proxy]

        # Validate and set proxy bypass settings
        proxybypass = (self.settings.get("proxybypass") or "").strip()
        if proxybypass and not proxy:
            return {"status": "error", "message": f"Proxy Bypass cannot be used without a proxy!"}
        if proxy and proxybypass:
            if self.is_valid_proxy_bypass(proxybypass) is False:
                return {"status": "error", "message": f"Proxy Bypass: '{proxybypass}' is not valid for NO_PROXY format"}
            parameters += ["-proxybypass", proxybypass]

        # Validate and set clearkeys sources
        clearkeys = (self.settings.get("clearkeys") or "").strip()
        if clearkeys:
            # Check if it's a valid URL or if a file exists
            if self.is_valid_url(clearkeys) or os.path.isfile(clearkeys) or os.path.isfile(os.path.join(path,clearkeys)):
                parameters += ["-clearkeys", clearkeys]
            else:
                return {"status": "error", "message": f"Clearkeys: The file/url '{clearkeys}' does not exist or is invalid"}

        # Validate and set cookies file
        cookies = (self.settings.get("cookies") or "").strip()
        if cookies:
            if os.path.isfile(cookies) or os.path.isfile(os.path.join(path,cookies)):
                parameters += ["-cookies", cookies]
            else:
                return {"status": "error", "message": f"Cookies: The file '{cookies}' does not exist!"}

        # Set subtitles value
        subtitles = (self.settings.get("subtitles") or False)
        if subtitles:
            parameters += ["-subtitles"]

        # Convert all paramaters into a string
        parameter_string = " ".join(parameters)

        profile = StreamProfile(
            name=profile_name,
            command=self.dw_path,
            parameters=parameter_string,
            locked=False,
            is_active=True,
        )
        profile.save()

        return {
            "status": "ok",
            "message": f"Created '{profile_name}' profile"
        }

    # Simply function for storing settings in db
    def persist_settings(self, updates: Dict[str, Any], clear: list[str] | None = None) -> dict:
        clear = clear or []
        with transaction.atomic():
            cfg, _ = PluginConfig.objects.select_for_update().get_or_create(key=self.plugin_key, defaults={"settings": {}})
        for key in clear:
            cfg.settings.pop(key, None)

        cfg.settings.update(updates)
        cfg.save(update_fields=["settings", "updated_at"])
        self.settings = cfg.settings
        return cfg.settings


    # Restores all fields to defaults
    def reset_plugin(self) -> Dict[str, Any]:
        keys = [
            "profile_name",
            "loglevel",
            "proxy",
            "proxybypass",
            "clearkeys",
            "cookies",
            "subtitles",
        ]

        default_values = {field["id"]: field.get("default") for field in self.fields}

        updates = {k: default_values.get(k) for k in keys if k in default_values}

        persisted = self.persist_settings(updates, clear=keys)

        return {
            "status": "stopped",
            "message": "Dispatchwrapparr plugin settings reset to defaults",
            "settings": persisted,
        }

    # Uninstalled dispatchwrapparr
    def uninstall(self):
        self.persist_settings({"local_version": None})
        if os.path.exists(self.dw_path):
            os.remove(self.dw_path)
            return {"status": "ok", "message": "Uninstalled Dispatchwrapparr"}
        else:
            return {"status": "error", "message": f"Path {self.dw_path} does not exist!"}

    # Main run function
    def run(self, action: str, params: dict, context: dict):
        self.settings = context.get("settings", {})
        if action == "install":
            return self.install()

        if action == "check_updates":
            return self.check_updates()

        if action == "create_profile":
            return self.create_profile()

        if action == "reset_plugin":
            return self.reset_plugin()

        if action == "uninstall":
            return self.uninstall()

        return {"status": "error", "message": f"Unknown action: {action}"}

