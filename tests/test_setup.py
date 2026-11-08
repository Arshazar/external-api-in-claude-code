import contextlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import setup_external_api as setup


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config with spaces" / "settings.json"

    def run_cli(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = setup.main(["--settings", str(self.path), "--provider", "console", *args])
        return code, output.getvalue(), errors.getvalue()

    def seed(self, raw):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(raw)

    def test_create_console_configuration(self):
        code, out, err = self.run_cli("--key", 'oc_sk_quote"\\$test')
        self.assertEqual(code, 0, err)
        env = json.loads(self.path.read_text())["env"]
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://opencode.ai/inference/anthropic")
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], 'oc_sk_quote"\\$test')
        self.assertEqual(env["ANTHROPIC_MODEL"], setup.DEFAULT_MODELS["sonnet"])
        self.assertNotIn("oc_sk_", out)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_preserve_settings_backup_and_idempotency(self):
        raw = b'{"permissions":{"allow":[]},"env":{"CUSTOM":"value","ANTHROPIC_API_KEY":"old","CLAUDE_CODE_USE_VERTEX":"1"}}'
        self.seed(raw)
        self.assertEqual(self.run_cli("--key", "oc_sk_test")[0], 0)
        backups = list(self.path.parent.glob("*.external-api-backup-*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), raw)
        data = json.loads(self.path.read_text())
        self.assertEqual(data["permissions"], {"allow": []})
        self.assertEqual(data["env"]["CUSTOM"], "value")
        self.assertEqual(data["env"]["ANTHROPIC_API_KEY"], "")
        self.assertEqual(data["env"]["CLAUDE_CODE_USE_VERTEX"], "")
        self.assertEqual(self.run_cli("--key", "oc_sk_test")[0], 0)
        self.assertEqual(len(list(self.path.parent.glob("*.external-api-backup-*.json"))), 1)

    def test_go_and_custom_aliases(self):
        self.assertEqual(self.run_cli("--key", "test", "--provider", "go", "--model", "minimax-m3", "--haiku-model", "claude-haiku-5-5")[0], 0)
        env = json.loads(self.path.read_text())["env"]
        self.assertEqual(env["ANTHROPIC_BASE_URL"], setup.BASE_URLS["go"])
        self.assertEqual(env["ANTHROPIC_DEFAULT_OPUS_MODEL"], "minimax-m3")
        self.assertEqual(env["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "claude-haiku-5-5")
        self.assertEqual(env["ANTHROPIC_SMALL_FAST_MODEL"], "claude-haiku-5-5")

    def test_sonnet_override_sets_startup_model(self):
        env = setup.configure({}, "test", "console", sonnet="custom")["env"]
        self.assertEqual(env["ANTHROPIC_MODEL"], "custom")

    def test_go_defaults_use_subscription_model(self):
        env = setup.configure({}, "test", "go")["env"]
        for alias in ("OPUS", "SONNET", "HAIKU"):
            self.assertEqual(env["ANTHROPIC_DEFAULT_" + alias + "_MODEL"], "minimax-m3")
        self.assertEqual(env["ANTHROPIC_MODEL"], "minimax-m3")

    def test_dry_run_does_not_write_or_disclose_secrets(self):
        self.seed(b'{"env":{"OTHER_SECRET":"unrelated-secret-value"}}')
        before = self.path.read_bytes()
        code, output, err = self.run_cli("--key", "oc_sk_secret", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertNotIn("oc_sk_secret", output)
        self.assertNotIn("unrelated-secret-value", output)
        self.assertIn("<redacted>", output)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(len(list(self.path.parent.iterdir())), 1)

    def test_dry_run_does_not_create_directory(self):
        self.assertEqual(self.run_cli("--key", "test", "--dry-run")[0], 0)
        self.assertFalse(self.path.parent.exists())

    def test_invalid_settings_are_untouched(self):
        for raw in (b'{broken', b'[]', b'{"env":[]}', b'{"env":null}', b'\xff'):
            with self.subTest(raw=raw):
                self.seed(raw)
                self.assertEqual(self.run_cli("--key", "test")[0], 1)
                self.assertEqual(self.path.read_bytes(), raw)
                self.assertEqual(len(list(self.path.parent.iterdir())), 1)

    def test_restore_exact_bytes_and_backup_current(self):
        source = Path(self.temp.name) / "backup.json"
        original = b'\xef\xbb\xbf{ "env": {"CUSTOM": "test"} }\r\n'
        source.write_bytes(original)
        self.seed(b'{broken')
        self.assertEqual(self.run_cli("--restore", str(source))[0], 0)
        self.assertEqual(self.path.read_bytes(), original)
        saved = list(self.path.parent.glob("*.external-api-backup-*.json"))
        self.assertEqual(saved[0].read_bytes(), b'{broken')

    def test_invalid_restore_is_untouched(self):
        self.seed(b'{}')
        source = Path(self.temp.name) / "bad.json"
        source.write_text("invalid")
        self.assertEqual(self.run_cli("--restore", str(source))[0], 1)
        self.assertEqual(self.path.read_bytes(), b'{}')

    def test_failed_replace_preserves_original_and_cleans_temporary(self):
        self.seed(b'{}')
        with patch.object(setup.os, "replace", side_effect=OSError("simulated failure")):
            code, _, _ = self.run_cli("--key", "test")
        self.assertEqual(code, 1)
        self.assertEqual(self.path.read_bytes(), b'{}')
        self.assertFalse(list(self.path.parent.glob(".external-api-*")))

    def test_config_dir_and_home_paths(self):
        for system in ("darwin", "linux", "win32"):
            with self.subTest(system=system), patch.object(sys, "platform", system), patch.object(setup.Path, "home", return_value=Path(self.temp.name)), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(setup.settings_path(), Path(self.temp.name) / ".claude" / "settings.json")
                with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.path.parent)}):
                    self.assertEqual(setup.settings_path(), self.path)

    def test_noninteractive_missing_key_fails_without_changes(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(sys.stdin, "isatty", return_value=False):
            code, _, error = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn("OPENCODE_API_KEY", error)
        self.assertFalse(self.path.exists())

    def test_environment_key_and_invalid_values(self):
        with patch.dict(os.environ, {"OPENCODE_API_KEY": "oc_sk_env"}):
            self.assertEqual(self.run_cli()[0], 0)
        for args in (("--key", "bad\nkey"), ("--key", "test", "--model", ""), ("--key", "test", "--model", "bad model")):
            self.assertEqual(self.run_cli(*args)[0], 1)

    def test_actual_process_cli(self):
        result = subprocess.run([sys.executable, str(Path(setup.__file__).resolve()), "--settings", str(self.path), "--key", "test", "--base-url", "https://gateway.example/api", "--model", "custom"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.path.read_text())["env"]["ANTHROPIC_MODEL"], "custom")

    def test_custom_endpoint_with_api_key_clears_previous_token(self):
        self.seed(b'{"env":{"ANTHROPIC_AUTH_TOKEN":"old-token","CUSTOM":"keep"}}')
        code, out, err = self.run_cli("--provider", "custom", "--base-url", "https://gateway.example/prefix/",
                                      "--model", "provider/model", "--auth", "api-key", "--key", "new-key")
        self.assertEqual(code, 0, err)
        env = json.loads(self.path.read_text())["env"]
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://gateway.example/prefix")
        self.assertEqual(env["ANTHROPIC_API_KEY"], "new-key")
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "")
        self.assertEqual(env["CUSTOM"], "keep")
        for alias in ("OPUS", "SONNET", "HAIKU"):
            self.assertEqual(env["ANTHROPIC_DEFAULT_" + alias + "_MODEL"], "provider/model")
        self.assertNotIn("new-key", out)

    def test_custom_provider_is_cli_default(self):
        with patch.dict(os.environ, {}, clear=True):
            with contextlib.redirect_stdout(io.StringIO()):
                code = setup.main(["--settings", str(self.path), "--key", "test",
                                   "--base-url", "https://gateway.example", "--model", "custom"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.path.read_text())["env"]["ANTHROPIC_BASE_URL"], "https://gateway.example")

    def test_custom_provider_requires_url_and_complete_model_mapping(self):
        for args in (("--model", "custom"), ("--base-url", "https://gateway.example"),
                     ("--base-url", "https://gateway.example", "--sonnet-model", "custom")):
            with self.subTest(args=args), patch.dict(os.environ, {}, clear=True):
                code, _, err = self.run_cli("--provider", "custom", "--key", "test", *args)
                self.assertEqual(code, 1, err)
                self.assertFalse(self.path.exists())

    def test_custom_aliases_without_shared_model(self):
        env = setup.configure({}, "test", base_url="https://gateway.example", opus="large",
                              sonnet="medium", haiku="small")["env"]
        self.assertEqual(env["ANTHROPIC_MODEL"], "medium")
        self.assertEqual(env["ANTHROPIC_SMALL_FAST_MODEL"], "small")

    def test_custom_environment_and_key_precedence(self):
        with patch.dict(os.environ, {"EXTERNAL_API_BASE_URL": "https://gateway.example",
                                    "EXTERNAL_API_KEY": "generic-key", "OPENCODE_API_KEY": "opencode-key"}):
            code, _, err = self.run_cli("--provider", "custom", "--model", "model")
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(self.path.read_text())["env"]["ANTHROPIC_AUTH_TOKEN"], "generic-key")
            self.assertEqual(self.run_cli("--provider", "custom", "--model", "model", "--key", "explicit-key")[0], 0)
            self.assertEqual(json.loads(self.path.read_text())["env"]["ANTHROPIC_AUTH_TOKEN"], "explicit-key")

    def test_local_gateway_and_switch_to_bearer(self):
        self.seed(b'{"env":{"ANTHROPIC_AUTH_TOKEN":"old","ANTHROPIC_API_KEY":"old"}}')
        code, _, err = self.run_cli("--provider", "custom", "--base-url", "http://localhost:8080",
                                  "--model", "local-model", "--key", "local")
        self.assertEqual(code, 0, err)
        env = json.loads(self.path.read_text())["env"]
        self.assertEqual(env["ANTHROPIC_API_KEY"], "")
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "local")
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "http://localhost:8080")

    def test_invalid_urls_do_not_write_or_expose_credentials(self):
        urls = ("ftp://gateway.example", "https://", "https://user:secret@gateway.example",
                "https://gateway.example?key=secret", "https://gateway.example/#secret",
                "https://gateway.example:bad", "https://gateway.example:99999", "https://bad host",
                "https://gateway.example\n", "https://[broken")
        for url in urls:
            with self.subTest(url=url):
                code, out, err = self.run_cli("--base-url", url, "--key", "test", "--dry-run")
                self.assertEqual(code, 1)
                self.assertNotIn("secret", out + err)
                self.assertFalse(self.path.exists())

    def test_api_key_preview_redacts_credential(self):
        code, out, err = self.run_cli("--auth", "api-key", "--key", "secret-key", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertNotIn("secret-key", out)
        self.assertIn('"ANTHROPIC_API_KEY": "<redacted>"', out)
        self.assertFalse(self.path.exists())

    def test_opencode_key_not_used_for_custom_provider(self):
        with patch.dict(os.environ, {"OPENCODE_API_KEY": "unrelated-key"}, clear=True), patch.object(sys.stdin, "isatty", return_value=False):
            code, _, err = self.run_cli("--provider", "custom", "--base-url", "https://gateway.example", "--model", "model")
        self.assertEqual(code, 1)
        self.assertIn("EXTERNAL_API_KEY", err)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
