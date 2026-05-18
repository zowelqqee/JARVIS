from actions import file_controller as file_module


def test_open_project_finds_repo_and_uses_requested_app(monkeypatch, tmp_path):
    project_dir = tmp_path / "JARVIS"
    project_dir.mkdir()
    (project_dir / ".git").mkdir()

    opened = {}

    def fake_open_target(target, app=""):
        opened["target"] = target
        opened["app"] = app
        return True, "ok"

    monkeypatch.setattr(file_module, "_SAFE_ROOTS", [tmp_path])
    monkeypatch.setattr(file_module, "_open_target", fake_open_target)

    result = file_module.open_project(name="jarvis", path=str(tmp_path), app="vscode")

    assert opened["target"] == project_dir
    assert opened["app"] == "vscode"
    assert "Opened project: JARVIS" in result


def test_describe_tree_shows_nested_structure(monkeypatch, tmp_path):
    project_dir = tmp_path / "repo"
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "main.py").write_text("print('hi')", encoding="utf-8")

    monkeypatch.setattr(file_module, "_SAFE_ROOTS", [tmp_path])

    tree = file_module.describe_tree(str(project_dir), max_depth=2)

    assert "repo/" in tree
    assert "src/" in tree
    assert "main.py" in tree
