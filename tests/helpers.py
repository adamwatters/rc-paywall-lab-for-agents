"""Shared fixtures for the lab's unit tests (stdlib unittest, no simulator needed).

A "lab home" is a temp copy of my/*.example.json + my/ui_config.json; `load_lab`
(re)imports lab.py against it, because lab.py resolves PAYWALL_LAB_HOME at import.
"""
import importlib
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MY_TEMPLATE = os.path.join(ROOT, "my")
DESIGNS = os.path.join(ROOT, "library", "designs")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def make_home(tmp, name="home"):
    home = os.path.join(tmp, name)
    os.makedirs(os.path.join(home, "variations"))
    for src, dst in (("config.example.json", "config.json"), ("products.example.json", "products.json"),
                     ("ui_config.json", "ui_config.json"),
                     ("config.example.json", "config.example.json"), ("products.example.json", "products.example.json")):
        shutil.copy(os.path.join(MY_TEMPLATE, src), os.path.join(home, dst))
    return home


def load_lab(home):
    """Import (or re-import) lab.py with PAYWALL_LAB_HOME pointing at `home`."""
    os.environ["PAYWALL_LAB_HOME"] = home
    if "lab" in sys.modules:
        return importlib.reload(sys.modules["lab"])
    return importlib.import_module("lab")


def read_json(path):
    with open(path) as f:
        return json.load(f)


def read_text(path, mode="r"):
    with open(path, mode) as f:
        return f.read()


def ui_config():
    ui = read_json(os.path.join(MY_TEMPLATE, "ui_config.json"))
    ui.pop("_comment", None)
    return ui


def products():
    return read_json(os.path.join(MY_TEMPLATE, "products.example.json"))


def list_designs():
    return sorted(d for d in os.listdir(DESIGNS) if os.path.isfile(os.path.join(DESIGNS, d, "generate.py")))


def generate_design(slug, home):
    """Copy a library design into home/variations/<slug> and run its generate.py the
    way lab.py does (cwd = variation dir, PAYWALL_LAB_ROOT/HOME in env)."""
    dest = os.path.join(home, "variations", slug)
    if not os.path.isdir(dest):
        shutil.copytree(os.path.join(DESIGNS, slug), dest,
                        ignore=shutil.ignore_patterns("screenshots", "README.md", "__pycache__"))
    env = {**os.environ, "PAYWALL_LAB_ROOT": ROOT, "PAYWALL_LAB_HOME": home}
    r = subprocess.run([sys.executable, os.path.join(dest, "generate.py")], cwd=dest, env=env,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"{slug}/generate.py failed:\n{r.stdout}\n{r.stderr}")
    return dest, read_json(os.path.join(dest, "paywall.json"))
