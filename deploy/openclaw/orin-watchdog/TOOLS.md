# Approved Tools

## Current mode: disabled commissioning

Allowed after explicit Phase 5 activation:

- execute only the fixed no-argument Python client
  `bin/orin_watchdog_check.py`;
- report the exact validated JSON response.

Denied:

- general shell or arbitrary command execution;
- command arguments, client selectors, dates, modes, or payloads;
- direct database, Shopify, model, worker, or scheduler access;
- file edits, browser automation, elevated execution, or agent spawning;
- access to another client's workspace, credentials, queue, or evidence.

The watchdog schedule remains disabled until Phase 4 scheduler ownership is
proven and the read-only socket boundary passes commissioning.

This agent never receives a database credential.
