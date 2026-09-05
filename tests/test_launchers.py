"""Run the real cache script against temporary fixtures, never the user's web tree."""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts.validate_release import validate_wheel


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "Node.js is required for frontend cache regression tests")
class FrontendCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="vinote-cache-fixture-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.write("scripts/frontend_cache.mjs", (ROOT / "scripts/frontend_cache.mjs").read_text(encoding="utf-8"))
        self.write("web/package.json", json.dumps({"name": "cache-fixture", "version": "1.0.0"}))
        self.write("web/package-lock.json", json.dumps({"name": "cache-fixture", "lockfileVersion": 3}))
        self.write("web/src/main.ts", "export const greeting = 'fixture';\n")
        self.write("web/public/logo.svg", "<svg></svg>\n")
        self.write("web/index.html", '<div id="root"></div>\n')
        self.write("web/vite.config.ts", "export default {};\n")
        self.write("web/tsconfig.json", '{"compilerOptions": {}}\n')
        self.write("web/postcss.config.js", "export default {};\n")
        self.write("web/tailwind.config.js", "export default {};\n")

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def cache(self, action, expected):
        result = subprocess.run(
            [NODE, str(self.root / "scripts/frontend_cache.mjs"), action],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, expected, f"{action}: {result.stdout}\n{result.stderr}")

    def ready_fixture(self):
        for name in ("vite", "typescript", "react", "react-dom"):
            self.write(f"web/node_modules/{name}/package.json", json.dumps({"name": name}))
        self.cache("mark-deps", 0)
        self.write("static-build/index.html", '<script src="/assets/app.js"></script>\n')
        self.write("static-build/assets/app.js", "console.log('fixture');\n")
        self.cache("mark-build", 0)

    def test_first_run_needs_install_and_build_then_stamps_allow_skip(self):
        self.cache("check-deps", 1)
        self.cache("check-build", 1)
        self.ready_fixture()
        self.cache("check-deps", 0)
        self.cache("check-build", 0)
        # Repeated launches do not invalidate the stamps themselves.
        self.cache("mark-deps", 0)
        self.cache("mark-build", 0)
        self.cache("check-deps", 0)
        self.cache("check-build", 0)

    def test_source_change_requires_build_without_reinstall(self):
        self.ready_fixture()
        self.write("web/src/main.ts", "export const greeting = 'changed';\n")
        self.cache("check-deps", 0)
        self.cache("check-build", 1)

    def test_public_asset_change_requires_build(self):
        self.ready_fixture()
        self.write("web/public/logo.svg", "<svg><path /></svg>\n")
        self.cache("check-build", 1)

    def test_build_configuration_changes_require_build(self):
        self.ready_fixture()
        for name in ("index.html", "vite.config.ts", "tsconfig.json", "postcss.config.js", "tailwind.config.js"):
            with self.subTest(config=name):
                path = self.root / "web" / name
                path.write_text(path.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
                self.cache("check-deps", 0)
                self.cache("check-build", 1)
                self.cache("mark-build", 0)

    def test_missing_entrypoint_requires_build(self):
        self.ready_fixture()
        (self.root / "static-build/index.html").unlink()
        self.cache("check-build", 1)

    def test_missing_built_asset_requires_build(self):
        self.ready_fixture()
        (self.root / "static-build/assets/app.js").unlink()
        self.cache("check-build", 1)

    def test_changed_built_asset_requires_build(self):
        self.ready_fixture()
        self.write("static-build/assets/app.js", "console.log('corrupt output');\n")
        self.cache("check-build", 1)

    def test_lock_change_requires_reinstall_and_rebuild(self):
        self.ready_fixture()
        self.write("web/package-lock.json", json.dumps({"name": "changed-lock", "lockfileVersion": 3}))
        self.cache("check-deps", 1)
        self.cache("check-build", 1)
        self.cache("mark-deps", 0)
        self.cache("check-deps", 0)
        self.cache("check-build", 1)

    def test_package_change_requires_reinstall_and_rebuild(self):
        self.ready_fixture()
        self.write("web/package.json", json.dumps({"name": "cache-fixture", "version": "2.0.0"}))
        self.cache("check-deps", 1)
        self.cache("check-build", 1)

    def test_missing_dependency_requires_reinstall(self):
        self.ready_fixture()
        (self.root / "web/node_modules/vite/package.json").unlink()
        self.cache("check-deps", 1)

    def test_corrupt_stamps_are_cache_misses(self):
        self.ready_fixture()
        self.write("web/node_modules/.vinote-install.json", "not json")
        self.write("static-build/.vinote-build.json", "not json")
        self.cache("check-deps", 1)
        self.cache("check-build", 1)

    def test_only_mtime_changes_do_not_invalidate_content_cache(self):
        self.ready_fixture()
        (self.root / "web/src/main.ts").touch()
        (self.root / "web/package-lock.json").touch()
        self.cache("check-deps", 0)
        self.cache("check-build", 0)


class PackageContentsTests(unittest.TestCase):
    def validate_fixture(self, names):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.whl"
            with ZipFile(path, "w") as archive:
                for name in names:
                    archive.writestr(name, "synthetic fixture")
            errors = []
            validate_wheel(path, errors)
            return errors

    def test_normal_backend_package_is_allowed(self):
        self.assertEqual(self.validate_fixture(["backend/main.py", "backend/services/note_search.py"]), [])

    def test_environment_development_and_demo_identity_files_are_rejected(self):
        for filename in (".env", "tests/demo.py", "backend/anp/client_did_keys/did.json", "backend/anp/key_private.pem"):
            with self.subTest(filename=filename):
                self.assertTrue(self.validate_fixture(["backend/main.py", filename]))

    def test_missing_backend_entrypoint_is_rejected(self):
        self.assertTrue(self.validate_fixture(["vinote.dist-info/METADATA"]))


class WindowsLauncherStaticTests(unittest.TestCase):
    def test_npm_commands_use_call_so_batch_execution_returns(self):
        """Source-level contract only; this does not launch Windows or start.bat."""
        source = (ROOT / "start.bat").read_text(encoding="utf-8")
        active = "\n".join(
            line for line in source.splitlines()
            if not re.match(r"\s*(?:::|rem(?:\s|$))", line, re.IGNORECASE)
        )
        self.assertRegex(active, r"(?im)^\s*call\s+npm(?:\.cmd)?\s+ci\s*$")
        self.assertRegex(active, r"(?im)^\s*call\s+npm(?:\.cmd)?\s+run\s+build\s*$")
        self.assertNotRegex(active, r"(?im)^\s*npm(?:\.cmd)?\s+(?:ci|run\s+build)\b")


if __name__ == "__main__":
    unittest.main()
