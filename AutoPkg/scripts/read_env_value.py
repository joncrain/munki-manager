#!/usr/bin/env python3
"""Print the value of KEY from a .env-style file (first match), or print nothing."""
from __future__ import annotations

import sys
from pathlib import Path


def _strip_key(line: str) -> str:
  s = line.strip()
  if s.lower().startswith("export "):
    s = s[7:].lstrip()
  return s


def main() -> None:
  if len(sys.argv) != 3:
    return
  path, want = Path(sys.argv[1]), sys.argv[2]
  if not path.is_file():
    return
  text = path.read_text(encoding="utf-8", errors="replace")
  if text.startswith("\ufeff"):
    text = text[1:]
  for raw in text.splitlines():
    line = raw.split("#", 1)[0]
    line = _strip_key(line)
    if not line or "=" not in line:
      continue
    k, _, v = line.partition("=")
    if k.strip() != want:
      continue
    v = v.replace("\r", "").strip()
    if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
      v = v[1:-1]
    print(v, end="")
    return


if __name__ == "__main__":
  main()
