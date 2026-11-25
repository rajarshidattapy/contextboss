"""Management CLI tests: subcommands over a real store, demo still intact."""
import json

from contextboss.cli import main


def run_cli(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_add_get_update_delete(capsys, tmp_path):
    db = str(tmp_path / "cli.db")
    code, out, _ = run_cli(capsys, "--db", db, "add", "remember the alamo",
                           "--tag", "history", "--pinned")
    assert code == 0
    eid = json.loads(out)["id"]

    code, out, _ = run_cli(capsys, "--db", db, "get", eid)
    assert json.loads(out)["content"] == "remember the alamo"

    code, out, _ = run_cli(capsys, "--db", db, "search", "alamo")
    assert json.loads(out)[0]["id"] == eid

    code, out, _ = run_cli(capsys, "--db", db, "update", eid, "--content", "new text")
    assert json.loads(out)["version"] == 2

    code, out, _ = run_cli(capsys, "--db", db, "inspect", eid)
    assert json.loads(out)["versions"] == [1, 2]

    code, out, _ = run_cli(capsys, "--db", db, "delete", eid)
    assert json.loads(out)["deleted"] is True
    code, out, err = run_cli(capsys, "--db", db, "delete", eid)
    assert code == 1


def test_stats_and_list(capsys, tmp_path):
    db = str(tmp_path / "cli2.db")
    run_cli(capsys, "--db", db, "add", "entry one")
    run_cli(capsys, "--db", db, "add", "entry two", "--namespace", "other")
    code, out, _ = run_cli(capsys, "--db", db, "stats")
    assert json.loads(out)["entries"] == 2
    code, out, _ = run_cli(capsys, "--db", db, "list", "--namespace", "other")
    assert "entry two" in out and "entry one" not in out


def test_assemble_respects_budget(capsys, tmp_path):
    db = str(tmp_path / "cli3.db")
    run_cli(capsys, "--db", db, "add", "filler words " * 200)
    code, out, err = run_cli(capsys, "--db", db, "--budget", "300", "--reserve", "50",
                             "assemble", "filler")
    assert code == 0
    assert "---" in err


def test_export_import_roundtrip(capsys, tmp_path):
    db = str(tmp_path / "cli4.db")
    dump = str(tmp_path / "dump.jsonl")
    run_cli(capsys, "--db", db, "add", "exportable fact", "--tag", "x")
    code, out, _ = run_cli(capsys, "--db", db, "export", dump)
    assert json.loads(out)["exported"] == 1

    db2 = str(tmp_path / "cli5.db")
    code, out, _ = run_cli(capsys, "--db", db2, "import", dump)
    assert json.loads(out)["imported"] == 1
    code, out, _ = run_cli(capsys, "--db", db2, "import", dump)
    assert json.loads(out)["skipped_existing"] == 1
    code, out, _ = run_cli(capsys, "--db", db2, "search", "exportable")
    assert "exportable fact" in out


def test_demo_still_default(capsys):
    code, out, _ = run_cli(capsys, "--no-color", "--budget", "400")
    assert code == 0
    assert "Budget by tier" in out
