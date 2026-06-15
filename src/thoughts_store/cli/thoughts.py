# src/thoughts_store/cli/thoughts.py
import os, click, orjson
from pathlib import Path
from thoughts_store.store.ndjson_store import NdjsonStore
from thoughts_store.models.thought import Thought
from thoughts_store.util.time import display_time
from dotenv import load_dotenv

load_dotenv()


def _journal_path() -> str:
    jp = os.getenv("JOURNAL_PATH")
    if not jp:
        raise SystemExit("JOURNAL_PATH が未設定です（.env に設定）")
    return jp


@click.group()
def cli():
    pass


@cli.command("add")
@click.option("--text", required=True, help="本文")
@click.option("--tags", default="", help="カンマ区切りタグ")
@click.option("--id", "tid", required=True, help="レコードID（t_YYYYMMDD_xxxx 等）")
@click.option("--author", default=os.getenv("THOUGHT_AUTHOR", "author"))
def add(text, tags, tid, author):
    store = NdjsonStore(_journal_path())
    t = Thought(
        id=tid, content=text, author=author, tags=[s for s in tags.split(",") if s]
    )
    rec = store.append(t.to_dict())
    click.echo(orjson.dumps(rec, option=orjson.OPT_INDENT_2).decode())


@cli.command("verify")
def verify():
    ok = NdjsonStore(_journal_path()).verify_chain()
    click.echo("OK" if ok else "BROKEN")


@cli.command("rebuild")
@click.option("--out", "outpath", default=None, help="再構築したNDJSONの出力パス")
def rebuild(outpath):
    jp = _journal_path()
    if not outpath:
        p = Path(jp)
        outpath = str(p.with_name(p.stem + ".rebuilt" + p.suffix))
    store = NdjsonStore(jp)
    newp = store.rebuild_to(outpath)
    click.echo(f"rebuilt -> {newp}")
    ok = NdjsonStore(newp).verify_chain()
    click.echo("VERIFY: " + ("OK" if ok else "BROKEN"))


@cli.command("tail")
@click.option("--n", default=5, help="末尾からの件数")
def tail(n):
    store = NdjsonStore(_journal_path())
    items = list(store.iter_records())
    for rec in items[-n:]:
        ct = rec.get("created_at")
        print(f"[{display_time(ct)}] {rec.get('id')}  {rec.get('content')}")


if __name__ == "__main__":
    cli()
