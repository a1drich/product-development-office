from office import stacks
from office.stacks import GUIDES, detect, load, parse, prompt_section

GUIDE = """---
name: Laravel
layer: Backend
detect: artisan, */artisan
---

# Laravel

Scope.

## Setting up a repo

Setup.

## Agent guidance

- Run `php artisan test`.

## Deploying

Deploy.
"""


def test_parses_the_header_and_only_the_agent_guidance(tmp_path):
    s = parse(tmp_path / "LARAVEL.md", GUIDE)
    assert (s.name, s.layer, s.detect) == ("Laravel", "Backend", ("artisan", "*/artisan"))
    assert s.guidance == "- Run `php artisan test`."


def test_a_file_without_a_header_or_patterns_is_not_a_guide(tmp_path):
    assert parse(tmp_path / "x.md", "# Notes\n") is None
    assert parse(tmp_path / "x.md", "---\nname: X\n---\n") is None


def test_detects_by_file_name_and_by_contents(tmp_path):
    guides = tmp_path / "guides"
    guides.mkdir()
    (guides / "LARAVEL.md").write_text(GUIDE)
    (guides / "TW.md").write_text(GUIDE.replace("name: Laravel", "name: Tailwind")
                                  .replace("detect: artisan, */artisan",
                                           "detect: */package.json ~ tailwindcss"))
    repo = tmp_path / "repo"
    (repo / "api").mkdir(parents=True)
    (repo / "web").mkdir()
    (repo / "web" / "package.json").write_text('{"dependencies": {"react": "19"}}')
    assert detect(load(guides), repo) == []
    (repo / "api" / "artisan").write_text("")
    (repo / "web" / "package.json").write_text('{"devDependencies": {"tailwindcss": "4"}}')
    assert [s.name for s in detect(load(guides), repo)] == ["Laravel", "Tailwind"]


def test_prompt_section_names_each_stack_or_says_none_match(tmp_path):
    s = parse(GUIDES / "X.md", GUIDE)
    assert "### Laravel (Backend, from the office's `docs/stack/X.md`)" in prompt_section([s])
    assert "No stack guide matches" in prompt_section([])


def test_every_guide_in_the_repo_is_valid_and_listed():
    index = (GUIDES / "README.md").read_text()
    guides = [p for p in GUIDES.glob("*.md") if p.name != "README.md"]
    assert guides
    for path in guides:
        s = stacks.parse(path, path.read_text())
        assert s, f"{path.name} has no valid header"
        assert s.guidance, f"{path.name} has no '## Agent guidance' section"
        assert f"]({path.name})" in index, f"{path.name} is missing from docs/stack/README.md"
