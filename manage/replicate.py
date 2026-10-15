#!/usr/bin/env python3
"""CouchDB → CouchDB copy through native replication (`_replicate`), database by database, then verification.

The target CouchDB pulls the data from the source: documents with all their revisions, attachments and
design docs; a re-run only copies the difference (catch-up before a cutover). The script adds what
replication does not do: database creation, `_security` copy, verification (document counts, winning
revision and attachment digests of every document).

Run it where both CouchDB are reachable (standard library only); passwords on stdin (source, then target):

    printf '%s\\n%s\\n' "$SRC_PASS" "$TGT_PASS" | python3 replicate.py \\
        --source http://127.0.0.1:5984 --source-user admin \\
        --source-from-target http://172.17.0.1:5984 \\
        --target http://127.0.0.1:15984 --target-user admin

--source / --target: addresses seen by the script; --source-from-target: the source as seen by the target
CouchDB (which runs the replication). System databases (`_users`, `_replicator`…) are skipped.
"""

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PAGE = 1000


class Couch:
    def __init__(self, url, user, password):
        self.url = url.rstrip("/")
        self.user, self.password = user, password
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()

    def req(self, method, path, body=None, timeout=60):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.url + path, data=data, method=method)
        r.add_header("Authorization", self.auth)
        r.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def get(self, path, **kw):
        status, payload = self.req("GET", path, **kw)
        if status != 200:
            raise RuntimeError(f"GET {path} → {status} {payload}")
        return payload


def q(db):
    return urllib.parse.quote(db, safe="")


def iter_docs(couch, db, include_docs):
    """Paginated _all_docs."""
    startkey = None
    while True:
        params = {"limit": PAGE + 1}
        if include_docs:
            params["include_docs"] = "true"
        if startkey is not None:
            params["startkey"] = json.dumps(startkey)
        rows = couch.get(f"/{q(db)}/_all_docs?{urllib.parse.urlencode(params)}", timeout=300)["rows"]
        yield from rows[:PAGE]
        if len(rows) <= PAGE:
            return
        startkey = rows[PAGE]["id"]


def fingerprint(row, include_docs):
    """Winning revision + attachment digests, reduced to a short fingerprint."""
    rev = row["value"]["rev"]
    if not include_docs:
        return rev, 0
    atts = (row.get("doc") or {}).get("_attachments") or {}
    digests = sorted((name, a.get("digest")) for name, a in atts.items())
    return hash((rev, tuple(digests))), len(atts)


def compare(src, tgt, db, include_docs):
    """Missing, extra or different documents (dict: the ICU order of _all_docs is not Python's)."""
    source, attachments = {}, 0
    for row in iter_docs(src, db, include_docs):
        source[row["id"]], n = fingerprint(row, include_docs)
        attachments += n
    extra = different = 0
    for row in iter_docs(tgt, db, include_docs):
        expected = source.pop(row["id"], None)
        if expected is None:
            extra += 1
        elif expected != fingerprint(row, include_docs)[0]:
            different += 1
    return len(source), extra, different, attachments


def replicate_db(src, tgt, db, source_from_target, timeout=3600):
    status, payload = tgt.req("PUT", f"/{q(db)}")
    if status not in (201, 202, 412):
        raise RuntimeError(f"creating {db} → {status} {payload}")
    security = src.get(f"/{q(db)}/_security")
    if security:
        status, payload = tgt.req("PUT", f"/{q(db)}/_security", security)
        if status != 200:
            raise RuntimeError(f"_security of {db} → {status} {payload}")

    def endpoint(url, couch):
        return {
            "url": f"{url.rstrip('/')}/{q(db)}",
            "auth": {"basic": {"username": couch.user, "password": couch.password}},
        }

    # The target node runs the replication: its own address is localhost.
    body = {"source": endpoint(source_from_target, src), "target": endpoint("http://127.0.0.1:5984", tgt)}
    status, payload = tgt.req("POST", "/_replicate", body, timeout=timeout)
    if status not in (200, 201, 202) or not (payload or {}).get("ok"):
        raise RuntimeError(f"_replicate of {db} → {status} {payload}")
    if payload.get("no_changes"):  # nothing to copy: `history` describes the previous session
        return 0, 0
    history = (payload.get("history") or [{}])[0]
    return history.get("docs_written", 0), history.get("doc_write_failures", 0)


def process_db(src, tgt, db, source_from_target, verify_only=False, include_docs=True, timeout=3600):
    """Replicate (unless verify_only) then verify one database; used by the CLI and the CouchDB Manager."""
    written = failures = 0
    if not verify_only:
        written, failures = replicate_db(src, tgt, db, source_from_target, timeout)
    si, ti = src.get(f"/{q(db)}"), tgt.get(f"/{q(db)}")
    missing, extra, different, atts = compare(src, tgt, db, include_docs)
    sec_ok = src.get(f"/{q(db)}/_security") == tgt.get(f"/{q(db)}/_security")
    ok = not (missing or extra or different or failures) and sec_ok and si["doc_count"] == ti["doc_count"]
    return {
        "database": db,
        "ok": ok,
        "source docs": si["doc_count"],
        "target docs": ti["doc_count"],
        "source deleted": si["doc_del_count"],
        "target deleted": ti["doc_del_count"],
        "attachments": atts,
        "written": written,
        "failures": failures,
        "missing": missing,
        "extra": extra,
        "different": different,
        "_security": "=" if sec_ok else "≠",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", required=True)
    p.add_argument("--source-user", required=True)
    p.add_argument("--source-from-target", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--target-user", required=True)
    p.add_argument("--db", action="append", help="only these databases (repeatable)")
    p.add_argument("--verify-only", action="store_true", help="verify without replicating")
    p.add_argument("--no-attachments-check", action="store_true", help="compare revisions without attachments")
    p.add_argument("--timeout", type=int, default=3600, help="max duration of one replication (s)")
    args = p.parse_args()

    src_pass = sys.stdin.readline().rstrip("\n")
    tgt_pass = sys.stdin.readline().rstrip("\n")
    src = Couch(args.source, args.source_user, src_pass)
    tgt = Couch(args.target, args.target_user, tgt_pass)

    dbs = args.db or [d for d in src.get("/_all_dbs") if not d.startswith("_")]
    include_docs = not args.no_attachments_check
    totals = {"databases": 0, "ok": 0, "mismatches": 0, "errors": 0, "written": 0, "attachments": 0}
    started = time.time()
    print(f"{len(dbs)} databases ({'verification only' if args.verify_only else 'replication + verification'})")

    for i, db in enumerate(dbs, 1):
        totals["databases"] += 1
        try:
            r = process_db(src, tgt, db, args.source_from_target, args.verify_only, include_docs, args.timeout)
            totals["written"] += r["written"]
            totals["attachments"] += r["attachments"]
            totals["ok" if r["ok"] else "mismatches"] += 1
            print(
                f"[{i}/{len(dbs)}] {'OK      ' if r['ok'] else 'MISMATCH'} {db}: docs {r['source docs']}/{r['target docs']} "
                f"deleted {r['source deleted']}/{r['target deleted']} attachments {r['attachments']} "
                f"written {r['written']} failures {r['failures']} missing {r['missing']} extra {r['extra']} "
                f"different {r['different']} _security {r['_security']}",
                flush=True,
            )
        except Exception as e:  # noqa: BLE001 — one failing database must not stop the others
            totals["errors"] += 1
            print(f"[{i}/{len(dbs)}] ERROR    {db}: {e}", flush=True)

    print(
        f"Done in {int(time.time() - started)} s — {totals['databases']} databases: {totals['ok']} OK, "
        f"{totals['mismatches']} with mismatches, {totals['errors']} errors; {totals['written']} documents written, "
        f"{totals['attachments']} attachments verified"
    )
    sys.exit(0 if totals["mismatches"] == 0 and totals["errors"] == 0 else 1)


if __name__ == "__main__":
    main()
