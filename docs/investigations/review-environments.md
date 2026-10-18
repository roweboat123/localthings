# Review environment findings, 2026-10-18

Fresh environments installed from the submitted `requirements-dev.txt` resolve
different Home Assistant versions depending on Python:

| Python | Home Assistant | pytest-homeassistant-custom-component |
| --- | --- | --- |
| 3.13.16 | 2026.2.3 | 0.13.316 |
| 3.14.8 | 2026.9.4 | 0.13.367 |

Both installed smartthings-local 0.1.24, Ruff 0.16.1 and ty 0.0.65. The
repository's CI runs Python 3.14; CONTRIBUTING also permits Python 3.13.

## Reproduction on the submitted commits

- #637, `b9c485da9606f2dab5c8b1a4f35a6325582e56f8`: Python 3.13 reproduces
  all six reported failures in `tests/test_number_bounds.py` and all three
  reported ty errors. The same nine number tests and type check pass on 3.14.
- #640, `7c6e8d5c7c2bad0d21c6f41ec99a279cab1c30e7`: the full suite on 3.13
  reproduces eight failures: those six number cases and two offline-startup
  cases in `tests/localthings/test_combined_oven.py`.
- #650, `3161d616a3f2cc3a22dd1c64d6510cf8c9bc5ddd`: the three compartment
  cases in `tests/localthings/test_fridge_cabinet_light.py` fail on 3.13;
  all nine tests in that file pass on 3.14.

## Findings and test corrections

Home Assistant 2026.2.3 does not include duration in NumberEntity's
`UNIT_CONVERTERS`; it does not offer the hour-unit override assumed by the
number tests. The corrected tests verify minutes on that version and verify
hour conversion when HA supports it. No runtime duration behavior is changed.

The older entity-registry API types `async_get` as possibly returning None.
Explicitly asserting that the row exists before inspecting its name satisfies
that contract and preserves the intended test assertion.

The fridge test applied an Observe update directly on the event loop, although
the transport normally applies it from another thread. The cache had the open
door but its scheduled HA push was still pending when the assertion ran on
2026.2.3. Applying the notification through `hass.async_add_executor_job` fixes
the test without changing cabinet-light behavior.

The combined-oven tests set `last_update_success = False` to simulate offline
startup while a discovery cache push was still queued. That push later marked
the coordinator successful again. Waiting for the pending push through a
temporary coordinator listener before simulating offline fixes those cases.

These findings explain the test discrepancy; they do not address the
maintainer's separate scope and design objections. Keep the original closed
PRs unchanged. Future oven submissions should be smaller and model-scoped;
the combined-device design and untimed-start workaround need discussion first.

The corrected combined-oven suite passes all 3,404 tests on both fresh
environments; the corrected fridge suite passes all 2,909 tests on both.
Formatting, lint and type checks pass as well. The corrections are retained on
`investigate/review-compatibility-oven` and
`investigate/review-compatibility-fridge`, not submitted to the closed PRs.

## Cooktop revision

#642 now limits the new mappings to TP6X_CT_16K plus the exact
DeviceType_NV9300K-/AA2 value, keeps the empty-hood check in the cooktop
registry, and restores generic discovery and coordinator logging. Commit
`20f393966e7af88067b508d4e49b4c87e10b698d` passes all 3,004 tests on both
fresh environments, plus formatting, lint and type checks. GitHub Validate
run 39168051330 also passed. The installed combined test build was not changed.
