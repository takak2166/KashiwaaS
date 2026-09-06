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
| [private-worker.md](private-worker.md) | My Machines worker names, launch policy, display name ↔ API `env.name` |
| [cursor-secrets.md](cursor-secrets.md) | Cursor API key type, host secret placement, 403 triage |
| [private-worker-e2e.md](private-worker-e2e.md) | Private Worker curl + Slack E2E verification |
| [production-cutover-runbook.md](production-cutover-runbook.md) | Production cutover to My Machines; rollback needs pre-migration release |
| [stacked-pr-workflow.md](stacked-pr-workflow.md) | Stacked PR boundaries for large bot refactors (agent discipline) |
| [e2e.md](e2e.md) | Minimal E2E with the stack up (Compose / CI dry-run) |

The legacy entry point [design.md](design.md) remains for backward compatibility (redirects to this index).
