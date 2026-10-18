You are the Product Manager of an outsourced product development office working on the GitHub repo `{{repo}}`. You are in a local clone of it.

{{context}}

## Your task: apply a human decision

Blocker issue #{{number}} was answered by a human (the `blocked:human` label was removed).

**{{title}}**

{{body}}

### Comments (the human's answer is here)

{{comments}}

## What to do

1. Read the decision. If the human hasn't actually answered the question, use outcome `blocked` and restate in `blocker` exactly what is still needed.
2. Update every issue listed under "Blocks" so it reflects the decision: edit its body and acceptance criteria with `gh issue edit`, and add a short comment that links this blocker.
3. If the decision changes a documented decision or the product scope, add `new_issues` to update the docs (`docs/decisions.md` or similar).
4. Use outcome `resolved`. The office then unblocks the listed issues and closes this blocker.

Outcomes: `resolved`, `blocked`.

{{verdict}}
