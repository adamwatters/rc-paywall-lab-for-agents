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


# A generate.py that touches every higher-level DSL builder (siblings, toggle, badge,
# selected override, footer links, local image asset). Tests only — not a design.
FIXTURE_GENERATOR = """\
import os, sys
sys.path.insert(0, os.environ["PAYWALL_LAB_ROOT"])
from paywall_dsl import *
reset_ids()
S = Strings()
pkgs = products()
write_png(os.path.join("assets", "bg.png"), 8, 16, lambda x, y: (x * 30, y * 15, 200, 255))

def cards(trial):
    out = []
    for i, p in enumerate(pkgs):
        badge = badge_overlay(S.add("badge", "FREE TRIAL"), "#FF5A5Fff") if trial else None
        body = stack([text(S.add("name_" + p["identifier"], p["name"]), w="fit"),
                      text(S.add("price", V_PRICE + " / " + V_PERIOD), w="fit")],
                     axis="horizontal", distribution="space_between", badge=badge,
                     overrides=[when_selected(border={"color": hexcol("#2F6BFFff"), "width": 2})])
        out.append(package(p["identifier"], body, selected=(i == 0)))
    return out

row = lambda: stack([text(S.add("toggle", "Start free trial"), w="fit"), tab_control()], axis="horizontal")
cta = purchase_button(stack([text(S.add("cta", "Continue"), color=WHITE)], background=color_background(BLACK)))
switch = trial_toggle([row()] + cards(False) + [cta], [row()] + cards(True) + [cta], track_on="#2F6BFFff")
plain = stack(cards(False) + [cta], name="Offers (no trial)")
eligibility_siblings(switch, plain)
head_a = stack([text(S.add("h_trial", "Try it free"), fsize=28)])
head_b = stack([text(S.add("h_plain", "Unlock everything"), fsize=28)])
eligibility_siblings(head_a, head_b)
content = stack([spacer(), image("bg.png", 8, 16, 40, 80), head_a, head_b, spacer(), switch, plain,
                 footer_links(S, terms_url="https://example.com/t", privacy_url="https://example.com/p")],
                h="fill", margin=edges(top=44, leading=16, trailing=16, bottom=30))
write(paywall(content, S))
"""


def generate_fixture(home, name="fixture"):
    """Write FIXTURE_GENERATOR into home/variations/<name> and run it the way lab.py
    does (cwd = variation dir, PAYWALL_LAB_ROOT/HOME in env)."""
    dest = os.path.join(home, "variations", name)
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, "generate.py"), "w") as f:
        f.write(FIXTURE_GENERATOR)
    env = {**os.environ, "PAYWALL_LAB_ROOT": ROOT, "PAYWALL_LAB_HOME": home}
    r = subprocess.run([sys.executable, os.path.join(dest, "generate.py")], cwd=dest, env=env,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"fixture generate.py failed:\n{r.stdout}\n{r.stderr}")
    return dest, read_json(os.path.join(dest, "paywall.json"))
