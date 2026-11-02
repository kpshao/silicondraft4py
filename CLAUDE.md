## Agent skills

### Issue tracker

Issues and specs live as GitHub issues on `kpshao/silicondraft4py`, managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles map to same-named labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Issue and PR descriptions

GitHub issue and pull request descriptions are bilingual: Chinese first, then the English version in a collapsed `<details><summary>English</summary>` block, matching the format used by issues #2 and #3. Keep both versions in sync.

### Issue closure

Before closing an issue, or merging a PR that closes one, update every acceptance-criteria checkbox (`- [ ]` → `- [x]`) in both the Chinese and English versions. Only tick criteria that are verified; leave deferred or failing criteria unchecked and say why. Do not close an issue while a criterion is unverified.

### Documentation language

`README.md`, `GLOSSARY.md`, and `docs/adr/*.md` are bilingual: Chinese first, then the English original in a collapsed `<details><summary>English</summary>` block at the end of the file. Chinese is the primary version and both versions are updated together in the same change. Keep canonical English domain terms, code identifiers, JSON keys, CLI flags, and file names untranslated.
