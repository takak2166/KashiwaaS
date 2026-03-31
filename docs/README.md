# KashiwaaS design documentation (index)

The former single long `design.md` is split by topic. The source of truth for behavior is the code and tests in this repository.

| Document | Contents |
|----------|----------|
| [architecture.md](architecture.md) | Overview, tech stack, Docker Compose excerpt, directory layout, design patterns |
| [runtime-config.md](runtime-config.md) | `AppConfig` / environment variables, security (auth, secrets) |
| [features.md](features.md) | Functional spec, data shape, schedules, error handling |
| [testing.md](testing.md) | Testing strategy, CI, local verification |
| [operations.md](operations.md) | Deployment, operations, scaling |
| [bot.md](bot.md) | KashiwaaS Bot (`@kashiwaas`) and Cursor API integration (summary) |
| [e2e.md](e2e.md) | Minimal E2E with the stack up (Compose / CI dry-run) |

The legacy entry point [design.md](design.md) remains for backward compatibility (redirects to this index).
