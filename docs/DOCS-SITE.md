# Docs site and user manual

Every target repo delivers an [MkDocs](https://www.mkdocs.org/) site with each change. It is how the owner reviews what the office builds. To set one up, see the [integration guide](INTEGRATION.md#add-the-docs-site-and-user-manual).

Every target repo delivers an MkDocs site, and its centerpiece is the **user manual and feature catalog** at `docs/manual/README.md`. It has one section per feature or page, saying what it's for and how to use it, with desktop and mobile screenshots. It is how you review what the office builds, and it doubles as the product's user manual.

- **Who maintains it:**
  - The PM puts "manual and screenshots updated" in the acceptance criteria of anything a user sees, and its practices review flags features with no manual section or stale screenshots.
  - The Designer drafts each feature's manual entry and the screens to capture.
  - Engineers update the manual, `docs/manual/pages.json` and any other docs pages they make stale, in the same PR as the code.
  - The tester fails a PR whose manual is missing or wrong, or whose `mkdocs build --strict` fails.
- **Always live:** while `office start` runs, it serves the site from the target's main clone at `http://127.0.0.1:8787` (the next free port up for each further repo the office runs), and refreshes the clone after every merge. MkDocs live-reloads, so the site always shows the latest manual and screenshots. If the server dies, the office restarts it. `office docs serve owner/name` serves it on its own.
- **Screenshots:** the tester captures every manual page at desktop and phone widths on each UI change, and the office posts the changed screens on the PR and the status issue. See [UI and UX testing](TESTING.md#ui-and-ux-testing).


---
[← Back to the README](../README.md)
