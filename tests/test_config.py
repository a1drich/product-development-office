import json

import pytest

from office.config import Config


def test_repo_overrides_apply_to_that_repo_only(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "limits": {"engineer": 3},
        "repos": {"acme/app": {"database_url": "postgres://app@localhost:5547/app",
                               "codex_sandbox": {"reviewer": "read-only"}}},
    }))
    cfg = Config.load(path)
    app = cfg.for_repo("acme/app")
    assert app.database_url.endswith(":5547/app")
    assert app.codex_sandbox == {"reviewer": "read-only", "tester": "danger-full-access"}
    assert app.limits["engineer"] == 3  # machine-wide
    assert cfg.for_repo("acme/site").database_url is None


@pytest.mark.parametrize("key", ["limits", "agent_ports", "databse_url"])
def test_machine_wide_or_unknown_settings_cannot_be_set_per_repo(tmp_path, key):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"repos": {"acme/app": {key: 1}}}))
    with pytest.raises(ValueError, match=key):
        Config.load(path)
