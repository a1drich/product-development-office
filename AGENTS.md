# Agent guidance

Read `CLAUDE.md` for what this project is and the invariants it must keep. `README.md` is the spec.

## Preventing documentation drift

The docs are the product until the code exists, and afterwards they are what the office's own agents read. Keep them true.

- **Docs change in the same commit as the behavior.** If a change alters a role, label, workflow step, command, invariant or decision, update every doc that describes it in that same commit. A commit that makes a doc wrong is incomplete.
- **One home per fact.** The README owns the design: roles, labels, workflow, blocker template, billing rules, decisions. `docs/SETUP.md` owns installation and deployment. `docs/INTEGRATION.md` owns onboarding an existing repo. Other files summarize and link to the owner instead of restating the details. When two docs disagree, fix the one that isn't the owner.
- **`CLAUDE.md` mirrors the README's invariants.** When an invariant in the README changes (labels, role-to-CLI mapping, merge and deploy rules, startup sequence, stop condition), update `CLAUDE.md` in the same commit.
- **Every markdown file is linked from the README's Documentation table.** Add a row when you add a doc and remove it when you delete one. Files a *target* repo is expected to have (such as `DESIGN.md`) are mentioned as plain text, not linked.
- **Label what isn't built.** Describe anything not yet implemented as **(planned)**. When it ships, remove the marker and replace any example output with real output. Never document a command, flag or file that doesn't exist without that marker.
- **Commands must be real.** Every command in the docs must either have been run or be marked planned. When the code adds or renames a command, update `CLAUDE.md`, the README and the guides together.
- **Run the check before committing:** `./scripts/check-docs.sh`. It fails if a markdown file isn't linked from the README or a relative link points at a missing file.
- **Keep `CLAUDE.md` current.** When the first code lands, replace its "Current state" section with the real build, lint and test commands.

## Other rules

- Read every file before publishing or pushing it. This repo is public.
- Never add names, IPs, domains or other details from the private reference repos. Use `example.com` and `owner/name` placeholders.
