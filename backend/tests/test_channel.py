"""发布通道:测试版判定与"从正式版复制数据"的安全性。"""
import json
import sqlite3

from app import channel


def test_preview_only_for_packaged_prerelease():
    assert channel.is_preview("1.5.0-alpha.1", frozen=True)
    assert not channel.is_preview("1.5.0", frozen=True)
    assert not channel.is_preview("1.5.0-alpha.1", frozen=False)


def _stable(tmp_path, db_type="sqlite"):
    stable = tmp_path / "QuestionBank"
    (stable / "static" / "media").mkdir(parents=True)
    (stable / "static" / "media" / "a.png").write_bytes(b"png")
    (stable / "logs").mkdir()
    (stable / "logs" / "app.log").write_text("log")
    db = stable / "app.db"
    conn = sqlite3.connect(db)
    conn.execute("pragma journal_mode=wal")
    conn.execute("create table t (v text)")
    conn.execute("insert into t values ('stable')")
    conn.commit()
    url = f"sqlite+aiosqlite:///{db.as_posix()}" if db_type == "sqlite" else "mysql+aiomysql://u:p@h/qb"
    config = {"db_url": url, "db_type": db_type, "secret_key": "s", "lan_share": True}
    (stable / "config.json").write_text(json.dumps(config))
    return stable, conn


def test_seed_copies_data_and_repoints_database(tmp_path):
    stable, open_conn = _stable(tmp_path)  # 正式版运行中(连接未关闭)也能一致复制
    preview = tmp_path / "QuestionBank-Preview"
    assert channel.seed_state(stable, preview) == "available"

    channel.seed_from_stable(stable, preview)
    open_conn.close()

    config = json.loads((preview / "config.json").read_text())
    assert config["db_url"] == f"sqlite+aiosqlite:///{(preview / 'app.db').as_posix()}"
    assert config["lan_share"] is False and config["secret_key"] == "s"
    assert (preview / "static" / "media" / "a.png").read_bytes() == b"png"
    assert not (preview / "logs").exists()
    copied = sqlite3.connect(preview / "app.db")
    assert copied.execute("select v from t").fetchall() == [("stable",)]
    copied.close()

    # 正式版配置原样不动。
    assert json.loads((stable / "config.json").read_text())["db_url"].startswith(f"sqlite+aiosqlite:///{stable.as_posix()}")
    assert channel.seed_state(stable, preview) == "not_needed"


def test_mysql_stable_is_not_copied_and_decline_is_remembered(tmp_path):
    stable, conn = _stable(tmp_path, db_type="mysql")
    conn.close()
    preview = tmp_path / "QuestionBank-Preview"
    assert channel.seed_state(stable, preview) == "mysql"
    channel.decline_seed(preview)
    assert channel.seed_state(stable, preview) == "not_needed"
    assert not (preview / "config.json").exists()


def test_nothing_to_seed_without_configured_stable(tmp_path):
    assert channel.seed_state(tmp_path / "missing", tmp_path / "preview") == "not_needed"
