# Runbook

## Current state

Disabled commissioning mode. No watchdog schedule or delivery is active.

## Future approved check

After Phase 4 scheduler ownership and Phase 5 commissioning pass, execute only:

```text
python3 bin/orin_watchdog_check.py
```

The client accepts no arguments. It sends one constant request over a private
Unix socket and receives one schema-validated JSON response.

Exit status:

- `0`: healthy or before-deadline pending;
- `4`: watchdog alert;
- `5`: watchdog service failure;
- any other nonzero status: invalid invocation or response.

Never retry an alert automatically. Report the exact receipt and leave all
production gates unchanged.
