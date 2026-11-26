import argparse
import re
from pathlib import Path


SECTIONS = {
    "# User Story": ("User Story", 60),
    "## Where": ("Where", 50),
    "# 🎯 Acceptance Criteria": ("Acceptance Criteria", None),
    "## Evidence and references": ("Evidence and references", 50),
}
LINK = re.compile(r"!?\[([^\]\n]+)\]\((?:[^()\n]|\([^()\n]*\))*\)")
SCENARIO = re.compile(r"^\*\*Scenario \d+:")


def words(text):
    visible = LINK.sub(r"\1", text)
    return sum(any(char.isalnum() for char in token) for token in visible.split())


def check(title, description):
    headings = []
    counts = [("Title", words(title), 12)]
    current = None
    scenarios = 0
    total = 0
    for line in description.splitlines():
        line = line.strip()
        if line in SECTIONS:
            headings.append(line)
            label, limit = SECTIONS[line]
            current = None
            if limit is not None:
                counts.append((label, 0, limit))
                current = len(counts) - 1
            continue
        if SCENARIO.match(line) and headings[-1:] == ["# 🎯 Acceptance Criteria"]:
            scenarios += 1
            counts.append((f"Scenario {scenarios}", 0, 45))
            current = len(counts) - 1
        size = words(line)
        total += size
        if size and current is None:
            raise ValueError(f"Text outside a recognized section or scenario: {line[:40]}")
        if current is not None:
            label, count, limit = counts[current]
            counts[current] = (label, count + size, limit)

    if headings != list(SECTIONS) or not scenarios:
        raise ValueError("Use the four template headings in order and at least one scenario.")
    return counts + [("Description", total, 250)]


def main():
    parser = argparse.ArgumentParser(description="Check Jira story word limits.")
    parser.add_argument("title")
    parser.add_argument("description", type=Path)
    args = parser.parse_args()
    try:
        counts = check(args.title, args.description.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        parser.exit(1, f"{exc}\n")
    for label, count, limit in counts:
        print(f"{label}: {count}/{limit}{' OVER' if count > limit else ''}")
    return int(any(count > limit for _, count, limit in counts))


if __name__ == "__main__":
    raise SystemExit(main())
