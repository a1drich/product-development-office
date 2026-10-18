## Finishing

End your final message with exactly one JSON object in a ```json fenced block, and nothing after it:

```json
{
  "outcome": "<one of the outcomes listed above>",
  "summary": "<two or three sentences: what you did and why>",
  "pr": null,
  "blocker": null,
  "new_issues": [],
  "depends_on": []
}
```

- `pr`: the pull request number, when your role created or worked on one; otherwise `null`.
- `blocker`: when the outcome is `blocked`, an object with `title` (short), `decision` (the question), `context`, `options` (a list of strings, each a choice and its tradeoff) and `recommendation`. Otherwise `null`. The office files the blocker issue for you, so don't create one yourself.
- `depends_on`: when the outcome is `waiting`, the numbers of the issues that must be closed (merged or done) before this one can continue. Otherwise `[]`. Use `waiting`, not `blocked`, when the only thing in the way is another issue that the office is already working on: the office requeues this issue automatically once those issues close.
- `new_issues`: follow-up issues to file, as `{"title", "body"}` objects. The office files them. Use this for bugs you found, or for work you split off. Check the open issues below first. If one already covers it, even under a different title, don't file it again: mention that issue's number in your `summary`, or comment on it with `gh issue comment` if you have evidence to add.
- Better practices: if you noticed something the repo should do better, such as stale or missing context in `AGENTS.md` or `docs/`, a gap in tests or CI, or a slow or flaky verify command, add it to `new_issues` with a title starting with `Practice: ` and a body that gives the evidence. At most one per run, and only if it's worth someone's time.

Open issues in the repo right now:

{{open_issues}}

Never change issue labels yourself, never merge, and never deploy or release. The office does the labels and merges based on your verdict. Deploys are always a human decision.
