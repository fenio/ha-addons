"""Tests for Unbound settings backup validation and file rollback."""

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


class _FakeFlask:
    def __init__(self, _name):
        self.config = {}

    def route(self, *_args, **_kwargs):
        return lambda function: function


fake_flask = types.ModuleType("flask")
fake_flask.Flask = _FakeFlask
fake_flask.jsonify = lambda value, *args, **kwargs: value
fake_flask.render_template = lambda *args, **kwargs: ""
fake_flask.request = types.SimpleNamespace()
sys.modules.setdefault("flask", fake_flask)

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
os.environ["UNBOUND_CONFIG_GEN_PATH"] = str(WEB_DIR / "config_gen.py")
spec = importlib.util.spec_from_file_location("unbound_app", WEB_DIR / "app.py")
unbound_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(unbound_app)


def _valid_backup():
    return {
        "format": unbound_app.SETTINGS_BACKUP_FORMAT,
        "version": unbound_app.SETTINGS_BACKUP_VERSION,
        "config": {
            key: schema["default"]
            for key, schema in unbound_app.config_gen.CONFIG_SCHEMA.items()
        },
        "blocklists": ["https://example.com/hosts"],
        "whitelist": ["allowed.example"],
        "local_records": [
            {"hostname": "server.home", "ip": "192.168.1.10"},
        ],
        "stub_zones": [
            {"name": "home", "addr": "192.168.1.1"},
        ],
        "custom_files": {"unbound-overlay.conf": "private-address: 10.0.0.0/8\n"},
    }


class BackupValidationTests(unittest.TestCase):
    def test_valid_backup_is_normalized(self):
        backup, errors = unbound_app.validate_settings_backup(_valid_backup())

        self.assertEqual([], errors)
        self.assertEqual("server.home", backup["local_records"][0]["hostname"])
        self.assertEqual(
            set(unbound_app.config_gen.CONFIG_SCHEMA), set(backup["config"])
        )

    def test_invalid_format_and_content_are_rejected(self):
        data = _valid_backup()
        data["version"] = 99
        data["local_records"] = [{"hostname": "missing-ip"}]
        data["custom_files"] = {"arbitrary.conf": "server:\n"}

        backup, errors = unbound_app.validate_settings_backup(data)

        self.assertIsNone(backup)
        self.assertTrue(any("Unsupported backup version" in error for error in errors))
        self.assertTrue(any("local_records" in error for error in errors))
        self.assertTrue(any("unknown files" in error for error in errors))

    def test_missing_config_values_use_current_defaults(self):
        data = _valid_backup()
        data["config"] = {"num_threads": 4}

        backup, errors = unbound_app.validate_settings_backup(data)

        self.assertEqual([], errors)
        self.assertEqual(4, backup["config"]["num_threads"])
        self.assertTrue(backup["config"]["enable_dnssec"])

    def test_blocklist_urls_cannot_be_curl_options(self):
        data = _valid_backup()
        data["blocklists"] = ["--config=/config/unbound.conf"]

        backup, errors = unbound_app.validate_settings_backup(data)

        self.assertIsNone(backup)
        self.assertTrue(any("HTTP or HTTPS" in error for error in errors))

    def test_custom_mode_requires_custom_config_file(self):
        data = _valid_backup()
        data["config"]["custom_config"] = True
        data["custom_files"] = {}

        backup, errors = unbound_app.validate_settings_backup(data)

        self.assertIsNone(backup)
        self.assertTrue(any("requires" in error for error in errors))


class BackupFileTests(unittest.TestCase):
    def test_export_includes_state_and_known_custom_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {
                "config": root / "config.json",
                "blocklists": root / "blocklists.json",
                "whitelist": root / "whitelist.json",
                "records": root / "local_records.json",
                "zones": root / "stub_zones.json",
                "custom": root / "unbound-overlay.conf",
            }
            paths["config"].write_text(json.dumps({"num_threads": 3}))
            paths["blocklists"].write_text('["https://example.com/hosts"]')
            paths["whitelist"].write_text('["allowed.example"]')
            paths["records"].write_text("[]")
            paths["zones"].write_text("[]")
            paths["custom"].write_text("private-address: 10.0.0.0/8\n")

            old_values = (
                unbound_app.config_gen.CONFIG_FILE,
                unbound_app.BLOCKLISTS_FILE,
                unbound_app.WHITELIST_FILE,
                unbound_app.LOCAL_RECORDS_FILE,
                unbound_app.STUB_ZONES_FILE,
                unbound_app.SETTINGS_BACKUP_FILES,
            )
            try:
                unbound_app.config_gen.CONFIG_FILE = str(paths["config"])
                unbound_app.BLOCKLISTS_FILE = str(paths["blocklists"])
                unbound_app.WHITELIST_FILE = str(paths["whitelist"])
                unbound_app.LOCAL_RECORDS_FILE = str(paths["records"])
                unbound_app.STUB_ZONES_FILE = str(paths["zones"])
                unbound_app.SETTINGS_BACKUP_FILES = {
                    "unbound-overlay.conf": str(paths["custom"]),
                }

                backup = unbound_app.create_settings_backup()
            finally:
                (
                    unbound_app.config_gen.CONFIG_FILE,
                    unbound_app.BLOCKLISTS_FILE,
                    unbound_app.WHITELIST_FILE,
                    unbound_app.LOCAL_RECORDS_FILE,
                    unbound_app.STUB_ZONES_FILE,
                    unbound_app.SETTINGS_BACKUP_FILES,
                ) = old_values

            self.assertEqual(3, backup["config"]["num_threads"])
            self.assertEqual(["allowed.example"], backup["whitelist"])
            self.assertIn("unbound-overlay.conf", backup["custom_files"])

    def test_snapshot_restores_replaced_and_deleted_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / "existing.json"
            created = Path(tmp) / "created.json"
            existing.write_bytes(b"old\n")
            existing.chmod(0o600)
            snapshot = unbound_app._snapshot_files([str(existing), str(created)])

            unbound_app._write_bytes_atomic(str(existing), b"new\n")
            unbound_app._write_bytes_atomic(str(created), b"created\n")
            unbound_app._restore_files(snapshot)

            self.assertEqual(b"old\n", existing.read_bytes())
            self.assertEqual(0o600, existing.stat().st_mode & 0o777)
            self.assertFalse(created.exists())


class BackupImportTests(unittest.TestCase):
    def _path_patches(self, root):
        return [
            patch.object(unbound_app.config_gen, "CONFIG_FILE", str(root / "config.json")),
            patch.object(
                unbound_app.config_gen, "UNBOUND_CONF", str(root / "unbound-generated.conf")
            ),
            patch.object(unbound_app, "BLOCKLISTS_FILE", str(root / "blocklists.json")),
            patch.object(
                unbound_app, "BLOCKLIST_STATUS_FILE", str(root / "blocklist_status.json")
            ),
            patch.object(unbound_app, "BLOCKLIST_CONF", str(root / "blocklist.conf")),
            patch.object(unbound_app, "WHITELIST_FILE", str(root / "whitelist.json")),
            patch.object(
                unbound_app, "LOCAL_RECORDS_FILE", str(root / "local_records.json")
            ),
            patch.object(
                unbound_app, "LOCAL_RECORDS_CONF", str(root / "local_records.conf")
            ),
            patch.object(unbound_app, "STUB_ZONES_FILE", str(root / "stub_zones.json")),
            patch.object(
                unbound_app, "OVERLAY_WARNING_FILE", str(root / "overlay_warning.txt")
            ),
            patch.object(
                unbound_app,
                "SETTINGS_BACKUP_FILES",
                {
                    "unbound.conf": str(root / "unbound.conf"),
                    "unbound-overlay.conf": str(root / "unbound-overlay.conf"),
                    "unbound-extra.conf": str(root / "unbound-extra.conf"),
                },
            ),
        ]

    def test_import_writes_validated_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patches = self._path_patches(root)
            for item in patches:
                item.start()
            self.addCleanup(lambda: [item.stop() for item in reversed(patches)])

            with (
                patch.object(
                    unbound_app.request, "get_json", return_value=_valid_backup(), create=True
                ),
                patch.object(
                    unbound_app.config_gen,
                    "apply_config",
                    return_value={"ok": True, "restart_required": False},
                ) as apply_config,
            ):
                response = unbound_app.api_settings_import()

            self.assertTrue(response["ok"])
            self.assertEqual(
                ["https://example.com/hosts"],
                json.loads((root / "blocklists.json").read_text()),
            )
            self.assertTrue((root / "unbound-overlay.conf").exists())
            self.assertTrue(response["blocklist_refresh_required"])
            apply_config.assert_called_once()

    def test_import_restores_previous_files_when_apply_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "blocklists.json").write_text('["old.example"]\n')
            patches = self._path_patches(root)
            for item in patches:
                item.start()
            self.addCleanup(lambda: [item.stop() for item in reversed(patches)])

            with (
                patch.object(
                    unbound_app.request, "get_json", return_value=_valid_backup(), create=True
                ),
                patch.object(
                    unbound_app.config_gen,
                    "apply_config",
                    return_value={"ok": False, "message": "invalid config"},
                ),
                patch.object(
                    unbound_app.config_gen,
                    "_reload_unbound",
                    return_value=(True, ""),
                ),
            ):
                response, status = unbound_app.api_settings_import()

            self.assertEqual(400, status)
            self.assertFalse(response["ok"])
            self.assertEqual(
                ["old.example"], json.loads((root / "blocklists.json").read_text())
            )

    def test_importing_no_blocklists_clears_compiled_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "blocklist.conf").write_text(
                'local-zone: "old.example." always_refuse\n'
            )
            backup = _valid_backup()
            backup["blocklists"] = []
            patches = self._path_patches(root)
            for item in patches:
                item.start()
            self.addCleanup(lambda: [item.stop() for item in reversed(patches)])

            with (
                patch.object(
                    unbound_app.request, "get_json", return_value=backup, create=True
                ),
                patch.object(
                    unbound_app.config_gen,
                    "apply_config",
                    return_value={"ok": True, "restart_required": False},
                ),
            ):
                response = unbound_app.api_settings_import()

            self.assertTrue(response["ok"])
            self.assertFalse(response["blocklist_refresh_required"])
            self.assertEqual("", (root / "blocklist.conf").read_text())


class ConfigReloadTests(unittest.TestCase):
    def test_reload_failure_restores_previous_config(self):
        config_gen = unbound_app.config_gen
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_file = root / "config.json"
            unbound_conf = root / "unbound.conf"
            old_config = {
                key: schema["default"]
                for key, schema in config_gen.CONFIG_SCHEMA.items()
            }
            new_config = dict(old_config, verbosity=2)
            config_file.write_text(json.dumps(old_config))
            unbound_conf.write_text("old config\n")

            def write_new_config(_config):
                unbound_conf.write_text("new config\n")
                return True, ""

            with (
                patch.object(config_gen, "CONFIG_FILE", str(config_file)),
                patch.object(config_gen, "UNBOUND_CONF", str(unbound_conf)),
                patch.object(config_gen, "BLOCKLIST_CONF", str(root / "blocklist.conf")),
                patch.object(
                    config_gen, "LOCAL_RECORDS_CONF", str(root / "local_records.conf")
                ),
                patch.object(config_gen, "write_and_validate", side_effect=write_new_config),
                patch.object(
                    config_gen,
                    "_reload_unbound",
                    side_effect=[(False, "control unavailable"), (True, "ok")],
                ),
            ):
                result = config_gen.apply_config(new_config)

            self.assertFalse(result["ok"])
            self.assertEqual("old config\n", unbound_conf.read_text())
            self.assertEqual(old_config, json.loads(config_file.read_text()))


if __name__ == "__main__":
    unittest.main()
