"""
Module  : tests/unit/test_healing_javascript.py
Author  : Anil Kalisetti
Purpose : Run the in-browser JavaScript used to fingerprint elements, under Node.js with a tiny
          fake DOM, so a typo in the script is caught without launching a browser.

Skipped when Node.js is not installed (GitHub-hosted runners include it).
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from framework.ui.healing.fingerprint import CANDIDATES_SCRIPT, DESCRIBE_SCRIPT

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")

_HARNESS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));

class El {
  constructor(tag, attrs = {}, text = '', parent = null) {
    this.tagName = tag.toUpperCase(); this._attrs = attrs; this.innerText = text; this.textContent = text;
    this.value = attrs.value || ''; this.id = attrs.id || '';
    this.classList = (attrs.class || '').split(' ').filter(Boolean);
    this.parentElement = parent; this.children = []; this.nodeType = 1;
    this.offsetWidth = attrs.hidden ? 0 : 10; this.offsetHeight = this.offsetWidth;
    if (parent) parent.children.push(this);
  }
  getAttribute(name) { return name in this._attrs ? this._attrs[name] : null; }
  getClientRects() { return this.offsetWidth ? [1] : []; }
}

const body = new El('body');
const form = new El('div', {class: 'login_form'}, '', body);
const button = new El('input', {id: 'signin-btn', 'data-test': 'login-button', type: 'submit', value: 'Login', class: 'submit-button btn_action'}, '', form);
const password = new El('input', {id: 'pass word', type: 'password', placeholder: 'Password'}, '', form);
const hidden = new El('input', {type: 'hidden', hidden: true}, '', form);
new El('span', {}, 'first', form);
const second = new El('span', {}, '  second   label ', form);
const all = [body, form, button, password, hidden, form.children[3], second];

globalThis.window = {};
globalThis.document = {body, getElementsByTagName: (tag) => all.filter((e) => e.tagName.toLowerCase() === tag)};

const run = (script, ...args) => new Function(script)(...args);
console.log(JSON.stringify({
  button: run(input.describe, button),
  span: run(input.describe, second),
  inputs: run(input.candidates, 'input'),
  spans: run(input.candidates, 'span'),
}));
"""


@pytest.fixture(scope="module")
def result() -> dict:
    payload = json.dumps({"describe": DESCRIBE_SCRIPT, "candidates": CANDIDATES_SCRIPT})
    done = subprocess.run(["node", "-e", _HARNESS], input=payload, capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_describe_reads_the_attributes_a_person_would_use(result):
    assert result["button"] == {
        "tag": "input", "id": "signin-btn", "name": "", "type": "submit", "role": "", "aria_label": "",
        "data_test": "login-button", "placeholder": "", "classes": ["submit-button", "btn_action"],
        "text": "Login", "parent_tag": "div",
    }  # fmt: skip


def test_text_is_trimmed_and_whitespace_collapsed(result):
    assert result["span"]["text"] == "second label"


def test_candidates_skip_invisible_elements(result):
    assert len(result["inputs"]) == 2  # the hidden input is not a candidate


def test_selector_prefers_the_test_attribute_then_the_id(result):
    assert [c["selector"] for c in result["inputs"]] == ['[data-test="login-button"]', "#pass\\ word"]


def test_selector_falls_back_to_a_structural_path(result):
    assert [c["selector"] for c in result["spans"]] == [
        "body > div > span:nth-of-type(1)",
        "body > div > span:nth-of-type(2)",
    ]
