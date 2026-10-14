import argparse
import json
import sys

from . import config


def main():
    p = argparse.ArgumentParser(prog="bjjvault", description="BJJ instructional vault")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="download, transcribe, organize and index a link right now")
    a.add_argument("urls", nargs="+")
    a.add_argument("--redo-notes", action="store_true", help="re-run Claude organizing even if cached")
    sub.add_parser("serve", help=f"run the web app + background worker on {config.BASE_URL}")
    sub.add_parser("reindex", help="rebuild notes, hubs and the search index from cached data")
    s = sub.add_parser("search", help="search the vault from the terminal")
    s.add_argument("query")
    s.add_argument("-n", type=int, default=5)
    c = sub.add_parser("clip", help="cut a clip")
    c.add_argument("video_id")
    c.add_argument("start", type=float)
    c.add_argument("end", type=float)
    args = p.parse_args()
    config.ensure_dirs()

    if args.cmd == "add":
        from . import download, pipeline
        for url in args.urls:
            for entry in download.expand(url):
                print(f"→ {entry['title'] or entry['url']}")
                pipeline.process(entry["url"], entry["playlist"], redo_notes=args.redo_notes,
                                 on_status=lambda s, d="": print(f"   {s} {d}", file=sys.stderr))
    elif args.cmd == "serve":
        from .web.app import main as serve
        serve()
    elif args.cmd == "reindex":
        from . import download, index, notes, organize
        for f in sorted(config.ORGANIZED.glob("*.json")):
            vid = f.stem
            meta, org = download.load_meta(vid), organize.load(vid)
            notes.write_instructional(vid, meta, org)
            print(f"{vid}: {index.index_video(vid, meta, org)} chunks")
        notes.rebuild_hubs()
    elif args.cmd == "search":
        from . import index
        from .util import fmt_ts
        for r in index.search(args.query, args.n):
            print(f"[{r['similarity']:.2f}] {r['instructor']} — {r['video_title']} @ {fmt_ts(r['start'])}-{fmt_ts(r['end'])}"
                  f" ({r['kind']}: {r['technique'] or r['chapter']})  {r['video_id']}")
    elif args.cmd == "clip":
        from . import clips
        print(json.dumps(clips.create_link(args.video_id, args.start, args.end), indent=2))


if __name__ == "__main__":
    main()
