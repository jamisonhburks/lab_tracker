"""import_publications — bulk-seed a lab's COVERED region from a BibTeX export (day-0 ignition).

Turning a lab's existing papers into `lab_profile` publications is the single highest-leverage
seeding step: it flips the coverage map from "all frontier — fog" into a real, prioritized agenda
BEFORE anyone logs in, and gives the thinker in-context grounding in the lab's own language. Each
entry's title (+ year) is tagged onto the modality×task×paradigm axes by lab_profile's heuristic
auto-tagger; refine tags later if needed. Dependency-free (a minimal BibTeX parse — no bibtexparser).

Usage:
  python import_publications.py papers.bib --by jamison [--profile casale-lab]
  python import_publications.py papers.bib --dry-run        # preview parse + auto-tags, write nothing
"""
import argparse
import re
import sys

import lab_profile


def _field(entry: str, name: str) -> str:
    """Extract a single BibTeX field value ({braced} or "quoted"), tolerating one nested-brace level."""
    m = (re.search(r"\b" + name + r"\s*=\s*\{((?:[^{}]|\{[^{}]*\})*)\}", entry, re.I | re.S)
         or re.search(r"\b" + name + r'\s*=\s*"([^"]*)"', entry, re.I | re.S))
    return re.sub(r"\s+", " ", re.sub(r"[{}]", "", m.group(1))).strip() if m else ""


def parse_bibtex(text: str) -> list:
    """[{title, year, author}] from a BibTeX string. Entries without a title are skipped."""
    entries = []
    for chunk in re.split(r"(?m)^\s*@", text):          # split on entry starts
        if "{" not in chunk:
            continue
        title = _field(chunk, "title")
        if not title:
            continue
        year = _field(chunk, "year")
        entries.append({"title": title,
                        "year": int(year) if year.isdigit() else None,
                        "author": _field(chunk, "author")})
    return entries


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bibfile", help="path to a .bib file (BibTeX)")
    ap.add_argument("--by", default=None, help="attribute all entries to this lab member")
    ap.add_argument("--profile", default=None,
                    help="lab profile id (default: $SUBSTRATE_LAB, or the sole profiles/*.yaml)")
    ap.add_argument("--dry-run", action="store_true", help="preview parse + auto-tags; write nothing")
    args = ap.parse_args(argv)

    try:
        text = open(args.bibfile, encoding="utf-8").read()
    except OSError as err:
        print(f"Could not read {args.bibfile}: {err}")
        return 1

    entries = parse_bibtex(text)
    if not entries:
        print("No BibTeX entries with a title found.")
        return 1

    print(f"Parsed {len(entries)} publication(s) from {args.bibfile}"
          + (f", attributing to {args.by}" if args.by else "") + ".")
    for e in entries:
        if args.dry_run:
            tags = lab_profile.auto_tag(e["title"])
            hit = " · ".join(f"{ax}:{'/'.join(v)}" for ax, v in tags.items() if v) or "no axis tags"
            print(f"  [dry] {e['title'][:66]}  → {hit}")
        else:
            print("  " + lab_profile.record_publication(
                e["title"], year=e["year"], ref="", by=args.by, profile_id=args.profile))
    if not args.dry_run:
        print("\nDone — check `coverage_map` / `lab_profile.render()`: it should now show a real "
              "agenda (scope minus covered), not fog.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
