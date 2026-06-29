# Agent-client REST contract (operator plane)

The shared client for canopy-web's agent workspace (`/api/agents`). This is the
**operator plane** only — identity, syncs, work-products, skills, tasks, and the
board-command drain. It deliberately carries **no** run/step/artifact/verdict
surface (that is a separate wave).

A non-Python agent (e.g. ACE, TS) can conform to this contract directly without
reading the Python client.

## Auth + base URL

- **Auth header:** `Authorization: Bearer <PAT>`.
- **PAT resolution (precedence):** explicit arg → `CANOPY_WEB_PAT` env →
  `~/.claude/canopy/workbench-token`. Mint one with `/canopy:canopy-web-pat-mint`.
- **Base URL (precedence):** explicit arg → `CANOPY_WEB_API_URL` env →
  `https://canopy-web-ujpz2cuyxq-uc.a.run.app` (prod default).
- **Content-Type:** `application/json` on bodies. Non-2xx responses are errors.

## Endpoints

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/api/agents/` | `{slug,name,email,description,persona,avatar_url}` | upsert identity |
| POST | `/api/agents/{slug}/syncs/` | `{period_start,period_end,title,summary,doc_url,self_grades,source}` | idempotent per period+source |
| POST | `/api/agents/{slug}/work-products/` | `{work_products:[{title,kind,url,description,tags,source}]}` | upsert by url |
| PUT | `/api/agents/{slug}/skills/` | `{skills:[{name,description,url,improvement_note}]}` | replaces catalog |
| POST | `/api/agents/{slug}/tasks/sync` | `{tasks:[{ext_id,title,next_action,status,owner,assigned,…}]}` | non-destructive upsert |
| GET | `/api/agents/{slug}/commands?status=pending` | — | drain queued board actions |
| POST | `/api/agents/{slug}/commands/{id}/apply` | `{result_note}` | mark a command applied |
| PATCH | `/api/agents/{slug}/tasks/{id}/` | partial task fields | store context (rationale/plan/status/…) |

## Reference implementation

- **Transport + auth:** `orchestrator/canopy_web.py` (stdlib `urllib`, injectable
  transport, single source of PAT/base-url resolution).
- **Typed client:** `orchestrator/agent_client.py` (`AgentClient` + `catalog_from_repo`).
- **CLI:** `canopy agent …` (`orchestrator/agent_cli.py`) — `register`, `sync`,
  `work`, `skills`, `tasks-sync`, `commands`, `apply`, `set`.
- **Repo-identity convenience layer:** `orchestrator/agent_web.py` (resolves
  identity from an agent repo's `.claude-plugin/plugin.json` + `config/agent.json`)
  and the `canopy agent-publish` CLI — both sit on the same `canopy_web` core.
