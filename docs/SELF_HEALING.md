<!-- Author: Anil Kalisetti -->
# Self-healing locators

**Problem.** A release renames `#login-button` to `#signin-btn`. The product works; every test that
clicks the button fails. Self-healing repairs the selector **at run time** and **tells you**, so the
suite keeps giving signal and you fix the selector on your schedule.

## How it works

```
find/click(locator)
   |-- wait `heal_after` seconds (default 3) for the original selector ---- found -> done
   '-- not found, and the locator may heal:
         1. FallbackStrategy     selectors the author listed:  css("#x", fallbacks=[...])
         2. FingerprintStrategy  closest visible look-alike to the stored fingerprint
         3. (LlmStrategy         placeholder, not enabled)
       first success wins -> test continues on the healed selector, a HealEvent is recorded
       none -> keep waiting normally, then fail exactly as plain Selenium would
```

### Safety rules (why a heal is trustworthy)
| Rule | Effect |
|---|---|
| Different tag never matches | a button is never healed into a link |
| Threshold (`heal_threshold`, 0.8) | not similar enough -> fail honestly |
| Margin (`heal_margin`, 0.1) | two near-identical candidates -> fail instead of guessing |
| Only interactions that REQUIRE the element heal (`find`, `click`, `type_text`, `text_of`) | `is_visible` / `is_absent` / `find_all` probes are never healed |
| `css(..., heal=False)` | opt-out for actions that move money or delete data |
| Healed locators never heal again | no healing loops |
| Record mode never heals | the baseline is recorded on a known-good build only |
| Baseline is read-only in normal runs | a broken page cannot poison it; parallel workers cannot race |

## Using it

```python
LOGIN_BUTTON = css("#login-button", fallbacks=['[data-test="login-button"]', 'input[type="submit"]'])
PAY_NOW      = css('[data-test="pay"]', heal=False)
```
Every `css(...)` locator on a page class gets a name (`LoginPage.LOGIN_BUTTON`) automatically; that
name is the key in the baseline file.

### 1. Record the baseline (once, on a known-good build; repeat after intended UI changes)
```bash
make record-locators          # pytest -m "ui and smoke" --record-locators -n 0
git diff config/locator_fingerprints.json     # review it, then commit
```
Until you record, only declared `fallbacks` can heal.

### 2. Run normally
Healing is on by default. Switches:

| Flag | Meaning |
|---|---|
| `--no-healing` | plain Selenium behaviour for this run |
| `--fail-on-heal` | exit code 1 if any locator healed (use as a release gate) |
| `--record-locators` | capture fingerprints (known-good build only) |
| `HEAL_THRESHOLD`, `HEAL_MARGIN`, `HEAL_AFTER`, `LOCATOR_BASELINE` | environment variables (also settable in `config/environments/*.yaml`) |

### 3. Review what healed
* Management report: **"Locators healed automatically (needs review)"** (old selector, new selector, how, score, test).
* `reports/locator_healing.json`, terminal section "self-healing locators", and the log lines `LOCATOR HEALED ...`.
* Fix the selector in the page class in a normal pull request. Nothing rewrites your code automatically.

## What it cannot do
* Heal changed **behaviour** (removed feature, new step in a flow): that should fail.
* Heal **dynamic** locators built at run time (for example one per product name): they have no name, so
  only fallbacks apply. Give such locators fallbacks, or keep them stable.
* Look into **iframes or shadow DOM** (first version).
* Be instant: a heal costs the `heal_after` wait plus one page scan; the happy path costs nothing.
* A slow page can in theory trigger a heal while the right element is still loading. The threshold and
  margin make a wrong pick unlikely, but raise `HEAL_AFTER` on slow environments.

## Extending
* New similarity rules: subclass `SimilarityScorer` (`framework/ui/healing/scoring.py`).
* New repair method: subclass `HealingStrategy` and add it in `LocatorHealer.from_settings`.
* LLM-assisted healing: `LlmStrategy` documents the conditions (data redaction, choose-from-list only,
  cost budget). It is deliberately not implemented.

## Verification status
Scoring, strategies, safety guards, audit trail, `BasePage` integration (fake Selenium), baseline store,
plugin, reports, and the in-browser JavaScript (under Node with a fake DOM) are tested offline;
10 deliberate bugs in this code were each caught. **Not yet run:** healing against a real browser and
real site. Expect to tune `heal_threshold` / fallbacks on your first live run.
