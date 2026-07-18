import base64
import os
import shutil
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path


def run_mdv(*arguments, env):
    executable = shutil.which("mdv")
    assert executable, "mdv must be installed before running E2E tests"
    return subprocess.run(
        [executable, *map(str, arguments)],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def token_free_env(tmp_path):
    env = os.environ.copy()
    env.pop("MDVIEW_TOKEN", None)
    env.pop("MDVIEW_BASE_URL", None)
    env["MDVIEW_CONFIG_DIR"] = str(tmp_path / "config")
    env["MDVIEW_DATA_DIR"] = str(tmp_path / "data")
    return env


def test_open_hands_the_exact_markdown_to_the_browser_without_a_token(tmp_path):
    markdown = "# Architecture\n\n```mermaid\nflowchart LR\n  A --> B\n```\n"
    document = tmp_path / "architecture.md"
    document.write_text(markdown, encoding="utf-8")
    captured_url = tmp_path / "browser-url.txt"
    browser = tmp_path / "capture-browser"
    browser.write_text(
        "#!/usr/bin/env python3\n"
        "import os, pathlib, sys\n"
        "pathlib.Path(os.environ['MDV_CAPTURE_URL']).write_text(sys.argv[1])\n",
        encoding="utf-8",
    )
    browser.chmod(0o755)
    env = token_free_env(tmp_path)
    env["BROWSER"] = str(browser)
    env["MDV_CAPTURE_URL"] = str(captured_url)

    result = run_mdv("open", document, env=env)

    assert result.returncode == 0, result.stderr
    assert f"Opened {document}" in result.stdout
    url = captured_url.read_text(encoding="utf-8")
    prefix = "https://mdview.io/#mvd=zip:"
    assert url.startswith(prefix)
    archive = zipfile.ZipFile(BytesIO(base64.b64decode(url.removeprefix(prefix))))
    assert archive.namelist() == ["architecture.md"]
    assert archive.read("architecture.md").decode("utf-8") == markdown


def test_help_version_and_key_inspection_work_without_a_token(tmp_path):
    env = token_free_env(tmp_path)

    help_result = run_mdv("--help", env=env)
    version_result = run_mdv("--version", env=env)
    keys_result = run_mdv("keys", "list", env=env)
    path_result = run_mdv("keys", "path", env=env)

    assert help_result.returncode == 0
    assert "open" in help_result.stdout
    assert version_result.returncode == 0
    assert version_result.stdout.startswith("mdv, version ")
    assert keys_result.returncode == 0
    assert keys_result.stdout.strip() == "No token configured."
    assert path_result.returncode == 0
    assert Path(path_result.stdout.strip()) == tmp_path / "config" / "keys.json"
