## Finishing

End your final message with exactly one JSON object in a ```json fenced block, and nothing after it:

```json
{
  "outcome": "<one of the outcomes listed above>",
  "summary": "<two or three sentences: what you did and why>",
  "pr": null,
  "blocker": null,
  "new_issues": []
}
```

- `pr`: the pull request number, when your role created or worked on one; otherwise `null`.
- `blocker`: when the outcome is `blocked`, an object with `title` (short), `decision` (the question), `context`, `options` (a list of strings, each a choice and its tradeoff) and `recommendation`. Otherwise `null`. The office files the blocker issue for you, so don't create one yourself.
- `new_issues`: follow-up issues to file, as `{"title", "body"}` objects. The office files them. Use this for bugs you found, or for work you split off.

Never change issue labels yourself, never merge, and never deploy or release. The office does the labels and merges based on your verdict. Deploys are always a human decision.
