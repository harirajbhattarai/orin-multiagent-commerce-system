# Runbook

Current state: disabled commissioning mode. No schedule or delivery is active.

After the automatic HCS scheduler proof passes, execute only:

```text
python3 bin/orin_hcs_watchdog_check.py
```

Exit `0` means healthy or before-deadline pending, `4` means alert, and `5`
means service failure. Never retry an alert automatically and never alter any
runtime gate.
