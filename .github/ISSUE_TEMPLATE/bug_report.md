---
name: Bug Report
about: Something isn't working as expected
title: '[BUG] '
labels: bug
assignees: ''
---

## Describe the Bug
A clear and concise description of what the bug is.

## Steps to Reproduce
1. Go to '...'
2. Click on '...'
3. See error

## Expected Behaviour
What you expected to happen.

## Actual Behaviour
What actually happened.

## Environment

| Item | Value |
|------|-------|
| Integration version | e.g. `1.0.0` |
| Home Assistant version | e.g. `2024.12.0` |
| Firmware version (`icVersion`) | e.g. `ICEthS1-2.0.197` |
| Installation method | HACS / Manual |

## Relevant Logs

Enable debug logging by adding this to your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.irrigation_caddy: debug
```

Then paste the relevant log output here:

```
(paste logs here)
```

## Raw `/status.json` Response
If relevant, paste the output of `http://<your-icaddy-host>/status.json` here:

```json
(paste JSON here)
```

## Additional Context
Add any other context about the problem here.
