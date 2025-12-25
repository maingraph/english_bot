import re
from pathlib import Path

FILES = [
    "Vocabulary-List-1-Complete.md",
    "Vocabulary-List-2-Complete.md",
    "Vocabulary-List-3-Complete.md",
]

MAX_CHARS = 3500  # safe below Telegram 4096 limit

def clean_cell(s: str) -> str:
    s = s.strip()
    s = s.replace("—", "")
    s = re.sub(r"\*\*(.*?)\*\*", r"\1", s)  # remove **bold**
    s = s.replace("\n", " ").replace("\r", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("|", "/")  # don't break our pipe-delimited format
    return s

def norm_list(x: str) -> str:
    x = clean_cell(x)
    if not x:
        return ""
    items = [t.strip() for t in x.split(",")]
    items = [t for t in items if t]
    return ",".join(items)

def parse_markdown_tables(md: str):
    rows = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # header + separator
        if line.startswith("|") and i + 1 < len(lines):
            sep = lines[i + 1].strip()
            if sep.startswith("|") and set(sep.replace("|", "").strip()) <= set("-: "):
                i += 2
                # data rows
                while i < len(lines) and lines[i].strip().startswith("|"):
                    rline = lines[i].strip()
                    if set(rline.replace("|", "").strip()) <= set("-: "):
                        i += 1
                        continue

                    parts = [p.strip() for p in rline.strip("|").split("|")]
                    if len(parts) >= 6:
                        word, definition, translation, syns, ants, example = parts[:6]

                        word = clean_cell(word)
                        word = re.sub(r"^\s*\d+\.\s*", "", word).strip()

                        definition = clean_cell(definition)
                        translation = clean_cell(translation)
                        syns = norm_list(syns)
                        ants = norm_list(ants)
                        example = clean_cell(example)

                        if word:
                            rows.append((word, definition, translation, syns, ants, example))
                    i += 1
                continue
        i += 1
    return rows

def main():
    all_rows = []
    for fn in FILES:
        p = Path(fn)
        if not p.exists():
            raise SystemExit(f"Missing file: {fn}")
        all_rows.extend(parse_markdown_tables(p.read_text(encoding="utf-8")))

    # de-duplicate by (word, definition)
    seen = set()
    dedup = []
    for r in all_rows:
        key = (r[0].lower(), r[1].lower())
        if key in seen:
            continue
        seen.add(key)
        dedup.append(r)

    # chunk into Telegram-sized /importwords messages
    messages = []
    current = "/importwords\n"
    for word, definition, translation, syns, ants, example in dedup:
        line = f"{word}|{definition}|{translation}|{syns}|{ants}|{example}".strip()
        if len(current) + len(line) + 1 > MAX_CHARS:
            messages.append(current.rstrip() + "\n")
            current = "/importwords\n" + line + "\n"
        else:
            current += line + "\n"
    if current.strip() != "/importwords":
        messages.append(current.rstrip() + "\n")

    # print for copy-paste
    print(f"# Rows: {len(dedup)}")
    print(f"# Messages: {len(messages)}")
    print()
    for idx, msg in enumerate(messages, start=1):
        print(f"### MESSAGE {idx}/{len(messages)}")
        print(msg)

if __name__ == "__main__":
    main()
