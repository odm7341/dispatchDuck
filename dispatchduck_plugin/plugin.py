import os
import stat
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
    name = "DispatchDuck Plugin"
    version = "1.0.1"
    description = "An installer/updater and stream profile generator for DispatchDuck"

    dd_path = "/data/dispatchduck/dispatchduck.py"
    dd_latest = "https://raw.githubusercontent.com/odm7341/dispatchDuck/refs/heads/main/VERSION"
    dd_url = "https://raw.githubusercontent.com/odm7341/dispatchDuck/refs/heads/main/dispatchduck.py"
    base_dir = Path(__file__).resolve().parent
    plugin_key = base_dir.name.replace(" ", "_").lower()

    def __init__(self):
        try:
            self.context = PluginConfig.objects.get(key=self.plugin_key)
            self.settings = self.context.settings
        except PluginConfig.DoesNotExist:
            self.context = None
            if os.path.isfile(self.dd_path):
                self.settings = {"local_version": self.check_local_version()}
            else:
                self.settings = {}

        if os.path.isfile(self.dd_path) is False or self.settings.get("local_version") is None:
            self.actions = [
                {"id": "install", "label": "Install DispatchDuck", "description": "Click 'Run' to install DispatchDuck, then click the refresh icon in the top right corner."}
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
            ]
            confirm_install = {
                "required": True,
                "title": "Install DispatchDuck?",
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
                "title": "Uninstall DispatchDuck?",
                "message": "After uninstallation, you can then delete this plugin. You will need to manually remove any DispatchDuck stream profiles from 'Settings' -> 'Stream Profiles'",
            }
            self.actions = [
                {"id": "create_profile", "label": "Create Stream Profile", "description": "Create a DispatchDuck stream profile using the current settings", "confirm": confirm_profile},
                {"id": "reset_plugin", "label": "Reset Profile Builder", "description": "Restore default settings for the profile builder", "confirm": confirm_reset},
                {"id": "check_updates", "label": "Check for Updates", "description": f"Installed Version: v{self.settings.get('local_version')}", "confirm": confirm_update},
                {"id": "uninstall", "label": "Uninstall DispatchDuck", "description": "Uninstall DispatchDuck and reset plugin to defaults", "confirm": confirm_uninstall},
                {"id": "tsduck_version", "label": "Check tsduck Version", "description": "Check the version of tsduck installed on your system"}
            ]

    # Validation functions
    def is_valid_url(self, url: str) -> bool:
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False

    
    # Versioning functions
    def check_local_version(self):
        if os.path.isfile(self.dd_path):
            try:
                result = subprocess.run(
                    ["python3", self.dd_path, "-v"],
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
        resp = requests.get(self.dd_latest)
        resp.raise_for_status()
        version = resp.text.strip()
        return version

    # Handles installation and updates
    def install(self):
        path = os.path.dirname(self.dd_path)
        os.makedirs(path, exist_ok=True)
        resp = requests.get(self.dd_url)
        resp.raise_for_status()
        with open(self.dd_path, "w", encoding="utf-8") as f:
            f.write(resp.text)
        # set executable
        st = os.stat(self.dd_path)
        os.chmod(self.dd_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.persist_settings({"local_version": self.check_local_version()})
        return {"status": "ok", "message": f"Installed Dispatchwrapparr v{self.settings.get('local_version')} to {self.dd_path}"}

    def check_updates(self):
        local_version = self.check_local_version()
        remote_version = self.check_remote_version()
        if local_version == remote_version:
            return {"status": "ok", "message": "Dispatchwrapparr is already up to date"}
        else:
            resp = requests.get(self.dd_url)
            resp.raise_for_status()
            with open(self.dd_path, "w", encoding="utf-8") as f:
                f.write(resp.text)
            # set executable
            st = os.stat(self.dd_path)
            os.chmod(self.dd_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            self.persist_settings({"local_version": self.check_local_version()})
            return {"status": "ok", "message": f"Updated Dispatchwrapparr from v{local_version} to v{remote_version}"}

    # Handles stream profile creation and form validation
    def create_profile(self):
        if (self.settings.get("profile_name") or None) is None:
            return {"status": "error", "message": "Please specify a profile name!"}
        path = os.path.dirname(self.dd_path)
        profile_name = self.settings.get("profile_name").strip()
        if StreamProfile.objects.filter(name__iexact=profile_name).first():
            return {"status": "error", "message": f"Profile '{profile_name}' already exists!"}

        parameters = [
            "-ua", "{userAgent}",
            "-i", "{streamUrl}"
        ]

        # Convert all paramaters into a string
        parameter_string = " ".join(parameters)

        profile = StreamProfile(
            name=profile_name,
            command=self.dd_path,
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
        if os.path.exists(self.dd_path):
            os.remove(self.dd_path)
            return {"status": "ok", "message": "Uninstalled Dispatchwrapparr"}
        else:
            return {"status": "error", "message": f"Path {self.dd_path} does not exist!"}


    # function to check if tsduck is installed
    def tsduck_version(self):
        try:
            result = subprocess.run(
                ["tsp", "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            output = result.stdout.strip()
            # Parse version from "tsp: TSDuck - The MPEG Transport Stream Toolkit - version 3.42-4421"
            if "version " in output:
                version_part = output.split("version ")[1]
                return version_part.strip()
            else:
                # Fallback: try to extract version number with regex pattern
                import re
                version_match = re.search(r'version\s+([0-9.-]+(?:-[0-9]+)?)', output)
                if version_match:
                    return version_match.group(1)
                return None
        except subprocess.CalledProcessError:
            return None
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

        if action == "tsduck_version":
            return self.tsduck_version()

        return {"status": "error", "message": f"Unknown action: {action}"}

