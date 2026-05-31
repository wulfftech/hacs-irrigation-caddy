# Contributing to hacs-irrigation-caddy

Thanks for taking the time to contribute! This is a community-maintained integration and all help is welcome.

## Ways to Contribute

- 🐛 **Bug reports** — open a [bug report issue](https://github.com/wulfftech/hacs-irrigation-caddy/issues/new?template=bug_report.md)
- 💡 **Feature requests** — open a [feature request issue](https://github.com/wulfftech/hacs-irrigation-caddy/issues/new?template=feature_request.md)
- 🔧 **Pull requests** — fix bugs or add features (see below)
- 📖 **Documentation** — improve the README or add examples
- 🧪 **Testing** — test on different firmware versions and report findings

## Development Setup

1. **Fork** this repository and clone your fork
2. Copy `custom_components/irrigation_caddy/` into your HA `custom_components/` directory
3. Restart Home Assistant and configure the integration

### Recommended Tools

- [VS Code](https://code.visualstudio.com/) with the [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python)
- [Home Assistant Dev Container](https://developers.home-assistant.io/docs/development_environment) for a full local HA environment
- [HACS](https://hacs.xyz/) installed in your test HA instance

## Pull Request Guidelines

1. **Branch from `main`** — keep your branch name descriptive (e.g. `fix/zone-stop`, `feat/rain-sensor`)
2. **One change per PR** — easier to review and revert if needed
3. **Update the version** in `custom_components/irrigation_caddy/manifest.json` following [SemVer](https://semver.org/)
4. **Test your changes** against a real Irrigation Caddy if possible, or document what you've verified
5. **Describe your changes** in the PR using the provided template

## API Notes

The Irrigation Caddy uses an undocumented local HTTP API. All verified endpoints are in `coordinator.py`. If you discover new behaviour, please document it with:

- Firmware version (from `/settingsVars.json` → `icVersion`)
- Raw request/response
- Which model you tested on

## Code Style

- Follow [PEP 8](https://peps.python.org/pep-0008/)
- Match the existing code patterns (type hints, `CoordinatorEntity`, `DataUpdateCoordinator`)
- Keep entity classes focused — one responsibility per class

## Versioning

This project follows [Semantic Versioning](https://semver.org/):

| Change | Version bump |
|--------|-------------|
| Bug fix | Patch — `1.0.x` |
| New entity / feature | Minor — `1.x.0` |
| Breaking change | Major — `x.0.0` |
