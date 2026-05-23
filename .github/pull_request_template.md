## Task / context
- Mission Control task: <link or id>
- Why: <what problem this PR solves>

## Scope
- <bullet 1>
- <bullet 2>

### Out of scope
- <explicitly list what is NOT included>

## Evidence / validation
- [ ] `make check` (or explain what you ran instead)
- [ ] E2E (if applicable): <cypress run / screenshots>
- Logs/links:
  - <link to CI run>

## Screenshots (UI changes)
| Desktop | Mobile |
| --- | --- |
| <img src="..." width="600" /> | <img src="..." width="300" /> |

## Docs impact

### Internal docs (this repo + parent platform)
- [ ] No internal docs changes required
- [ ] Internal docs updated: <paths/links>

### Partner API docs (chimichangamonster/vantageclaw-docs)
Required when this PR touches anything partner-facing — partner router endpoints, schemas, scopes, webhook event vocabulary, signature/retry/timeout semantics, error shapes.

- [ ] N/A — this PR doesn't touch partner-facing surface
- [ ] Spec auto-sync sufficient — OpenAPI sync workflow handles it (small schema tweak, new optional field, internal refactor with no contract change)
- [ ] Conceptual docs PR needed — opened at: <link to vantageclaw-docs PR>
- [ ] Conceptual docs PR will follow in a separate change — tracked in: <issue/note link>

**Heuristic:** if a partner couldn't figure out how to use this change by reading the auto-synced OpenAPI spec alone, conceptual docs need updating. Run `/docs-partner` on the parent repo to surface candidates.

## Risk / rollout notes
- Risk level: low / medium / high
- Rollback plan (if needed): <steps>

## Checklist
- [ ] Branch created from `origin/master` (no unrelated commits)
- [ ] PR is focused (one theme)
- [ ] No secrets in code/logs/docs
- [ ] Docs impact section above is filled out (not skipped)
