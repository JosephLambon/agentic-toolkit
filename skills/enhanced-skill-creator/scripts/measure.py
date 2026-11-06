#!/usr/bin/env python3
"""Show what a skill costs in context, and check its file references.

Usage: python3 measure.py SKILL_DIR

Prints the size of each part and when it loads, then warns about bundled
files SKILL.md never mentions (Claude won't know to read them) and paths
SKILL.md mentions that don't exist. Tokens are estimates (characters / 4).
Warnings are hints: a file named only inside a script will also trip them.
Skips evals/ and hidden files, which never load. Exits 1 if SKILL.md is missing.
"""
import argparse
import re
import sys
from pathlib import Path

SKIP_PARTS = {"evals", "__pycache__", "node_modules"}
TEXT_SUFFIXES = {".md", ".txt", ".py", ".sh", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".html", ".css"}
# A bundled path, not one inside another folder (e.g. another skill's scripts/).
PATH_RE = re.compile(r"(?<![\w/.-])((?:references|assets|scripts)/[\w./-]*\w)")


def tokens(text):
    return round(len(text) / 4)


def split_frontmatter(text):
    match = re.match(r"^---\n(.*?)\n---\n?(.*)\Z", text, re.S)
    return (match.group(1), match.group(2)) if match else ("", text)


def parse_description(frontmatter):
    """Read `description` without a YAML dependency.

    Handles plain, quoted, > and | values, including ones wrapped onto indented
    lines. Doesn't unescape '' or \\" (off by a character at most).
    """
    lines = frontmatter.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("description:"):
            continue
        value = line[len("description:"):].strip()
        continued = []
        for following in lines[i + 1:]:
            if following and not following[0].isspace():
                break
            if following.strip():
                continued.append(following.strip())
        if value[:1] in (">", "|"):
            return (" " if value[0] == ">" else "\n").join(continued)
        value = " ".join([value] + continued)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            return value[1:-1]
        return value
    return ""


def bundled_files(skill_dir):
    for path in sorted(skill_dir.rglob("*")):
        rel = path.relative_to(skill_dir)
        if path.is_dir() or rel.as_posix() == "SKILL.md":
            continue
        if any(part in SKIP_PARTS or part.startswith(".") for part in rel.parts):
            continue
        yield rel


def measure(skill_dir):
    skill_dir = Path(skill_dir)
    text = (skill_dir / "SKILL.md").read_text()
    frontmatter, body = split_frontmatter(text)
    description = parse_description(frontmatter)
    files, unmentioned = [], []
    for rel in bundled_files(skill_dir):
        path, posix = skill_dir / rel, rel.as_posix()
        entry = {"path": posix, "bytes": path.stat().st_size, "words": None, "tokens": None}
        if path.suffix in TEXT_SUFFIXES:
            content = path.read_text(errors="replace")
            entry.update(words=len(content.split()), tokens=tokens(content))
        files.append(entry)
        named = re.search(rf"(?<![\w.-]){re.escape(rel.name)}(?![\w.-]*\w)", text)
        if posix not in text and not named:
            unmentioned.append(posix)
    missing = sorted(p for p in set(PATH_RE.findall(text)) if not (skill_dir / p).exists())
    return {
        "description_chars": len(description),
        "description_tokens": tokens(description),
        "body_words": len(body.split()),
        "body_tokens": tokens(body),
        "files": files,
        "unmentioned": unmentioned,
        "missing": missing,
    }


def format_report(r):
    lines = [
        f"description: {r['description_chars']} chars, ~{r['description_tokens']} tokens (every session's skill list)",
        f"SKILL.md body: {r['body_words']} words, ~{r['body_tokens']} tokens (each time the skill triggers)",
    ]
    for f in r["files"]:
        when = "run; loads only if read" if f["path"].startswith("scripts/") else "only when read"
        size = f"{f['words']} words, ~{f['tokens']} tokens" if f["words"] is not None else f"{f['bytes']} bytes"
        lines.append(f"{f['path']}: {size} ({when})")
    warnings = [f"- {p} is never mentioned in SKILL.md, so Claude won't know to read it" for p in r["unmentioned"]]
    warnings += [f"- SKILL.md mentions {p}, which doesn't exist" for p in r["missing"]]
    lines.append("warnings:" if warnings else "warnings: none")
    return "\n".join(lines + warnings)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Show a skill's context cost and check its file references.")
    parser.add_argument("skill_dir", type=Path)
    args = parser.parse_args(argv)
    if not (args.skill_dir / "SKILL.md").is_file():
        print(f"No SKILL.md in {args.skill_dir}", file=sys.stderr)
        return 1
    print(format_report(measure(args.skill_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
