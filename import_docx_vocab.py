import argparse
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from duel_ladder_bot.db import DB
from duel_ladder_bot.config import DB_PATH


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def _clean_cell(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("\u00a0", " ")
    s = s.replace("—", " ")
    s = re.sub(r"\s+", " ", s).strip()
    # remove leading "1. " numbering if present
    s = re.sub(r"^\s*\d+\.\s*", "", s).strip()
    return s


def _split_list(s: str) -> list[str]:
    s = _clean_cell(s)
    if not s:
        return []
    s = s.replace("•", ";")
    parts: list[str] = []
    for chunk in s.split(";"):
        for p in chunk.split(","):
            p = _clean_cell(p)
            if p:
                parts.append(p)
    out: list[str] = []
    for p in parts:
        if p not in out:
            out.append(p)
    return out


def _docx_document_xml(path: Path) -> str:
    with zipfile.ZipFile(path, "r") as zf:
        with zf.open("word/document.xml") as f:
            return f.read().decode("utf-8", errors="replace")


def _extract_3col_rows(doc_xml: str) -> list[tuple[str, str, str]]:
    root = ET.fromstring(doc_xml)
    out: list[tuple[str, str, str]] = []
    for tbl in root.findall(".//w:tbl", NS):
        for tr in tbl.findall("./w:tr", NS):
            cells = []
            for tc in tr.findall("./w:tc", NS):
                texts = [t.text or "" for t in tc.findall(".//w:t", NS)]
                cell_text = _clean_cell("".join(texts))
                cells.append(cell_text)
            if len(cells) < 3:
                continue
            a, b, c = cells[0], cells[1], cells[2]
            if not a:
                continue
            # header detection
            header0 = a.lower()
            header1 = b.lower()
            if header0 in {"word", "word/phrase", "phrase"} and "synonym" in header1:
                continue
            out.append((a, b, c))
    return out


def import_docx_files(db: DB, files: list[Path]) -> tuple[int, int]:
    """
    Returns (inserted, skipped).
    """
    inserted = 0
    skipped = 0
    seen: set[tuple[str, str, str]] = set()

    for p in files:
        doc_xml = _docx_document_xml(p)
        for word, syns_raw, ants_raw in _extract_3col_rows(doc_xml):
            word = _clean_cell(word)
            syns = _split_list(syns_raw)
            ants = _split_list(ants_raw)
            if not word:
                skipped += 1
                continue
            key = (word.lower(), ",".join([s.lower() for s in syns]), ",".join([a.lower() for a in ants]))
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            db.add_word(
                word=word,
                definition="",
                translation="",
                synonyms=syns,
                antonyms=ants,
                example="",
            )
            inserted += 1

    return inserted, skipped


def main() -> None:
    ap = argparse.ArgumentParser(description="Import vocab from .docx synonym/antonym tables into SQLite.")
    ap.add_argument("files", nargs="+", help="Paths to .docx files")
    ap.add_argument("--db", default=DB_PATH, help=f"SQLite path (default: {DB_PATH})")
    ap.add_argument("--wipe", action="store_true", help="Wipe vocab table before importing")
    args = ap.parse_args()

    db = DB(args.db)
    before = db.count_words()
    if args.wipe:
        db.wipe_words()
        before = 0

    files = [Path(f) for f in args.files]
    inserted, skipped = import_docx_files(db, files)
    after = db.count_words()

    print(f"DB: {args.db}")
    print(f"Before: {before}")
    print(f"Inserted: {inserted}")
    print(f"Skipped: {skipped}")
    print(f"After: {after}")


if __name__ == "__main__":
    main()


