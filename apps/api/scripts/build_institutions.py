"""Rebuild ``src/app/domain/data/institutions.csv`` with every 지방자치단체, its council and every
시도 교육청, keeping the curated rows (and their codes and aliases) as they are.

Source: 행정안전부 행정동코드 as bundled in PublicDataReader 1.1.1 (``raw/code_hdong.json``, last
change 2023-05-01). The file predates three changes, applied below by hand:

* 강원도 → 강원특별자치도 (2023-06-11): 시도 code 42 → 51, 시군구 codes keep their last digits.
* 대구광역시 군위군 (2023-07-01): moved from 경상북도 (47720) to 대구광역시 (27720).
* 전라북도 → 전북특별자치도 (2024-01-18): the same renumbering, 45 → 52.

인천광역시's reorganisation of 2026-07-01 (제물포구·영종구·검단구) is not in the file and not added
here: the codes were not at hand. 30 days of 조달청 data is the check for what is missing.

Usage::

    pip download PublicDataReader==1.1.1.post2 --no-deps -d /tmp/pdr
    unzip -o /tmp/pdr/*.whl 'PublicDataReader/raw/code_hdong.json' -d /tmp/pdr
    uv run python scripts/build_institutions.py /tmp/pdr/PublicDataReader/raw/code_hdong.json
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parents[1] / "src/app/domain/data/institutions.csv"
FIELDS = ["code", "name", "kind", "sido", "sigungu", "region_code", "executive_code", "aliases"]

RENAMED_SIDO = {"42": ("51", "강원특별자치도"), "45": ("52", "전북특별자치도")}
MOVED_SIGUNGU = {"47720": ("27720", "27", "대구광역시")}  # 군위군
# 행정시 of 제주: no council of their own. 세종 has no 시군구 at all.
NO_COUNCIL = {"50110", "50130"}
# 특례시 (2022-01-13; 화성 2025-01-01) call themselves by that name in documents.
SPECIAL_CITIES = {
    "41110": "수원",
    "41280": "고양",
    "41460": "용인",
    "48120": "창원",
    "41590": "화성",
}
KIND_ORDER = {"local_gov": 0, "council": 1, "education_office": 2, "public_agency": 3}


def _rows(path: str) -> list[dict[str, str | None]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    keys = list(data)
    n = len(data[keys[0]])

    def clean(v: object) -> str | None:
        return v if isinstance(v, str) else None  # the file writes NaN for empty cells

    return [{k: clean(data[k][str(i)]) for k in keys} for i in range(n)]


def build(hdong_json: str) -> list[dict[str, str]]:
    sido: dict[str, str] = {}
    sigungu: list[tuple[str, str, str]] = []  # (region code, sido name, sigungu name)
    for r in _rows(hdong_json):
        if r["말소일자"] or r["읍면동명"]:
            continue
        code, sido_code, name = r["시군구코드"] or "", r["시도코드"] or "", r["시도명"] or ""
        if not r["시군구명"]:
            if code.endswith("000") and not name.endswith("출장소"):
                new_code, new_name = RENAMED_SIDO.get(sido_code, (sido_code, name))
                sido[new_code] = new_name
            continue
        sg = r["시군구명"]
        # Autonomous units only: skip 행정구 ("수원시 장안구") and 출장소.
        if " " in sg or "출장소" in sg or not sg.endswith(("시", "군", "구")):
            continue
        if code in MOVED_SIGUNGU:
            code, _, name = MOVED_SIGUNGU[code]
        elif sido_code in RENAMED_SIDO:
            new_sido, name = RENAMED_SIDO[sido_code]
            code = new_sido + code[2:]
        sigungu.append((code, name, sg))

    rows: list[dict[str, str]] = []
    for sido_code, name in sido.items():
        region = f"{sido_code}000"
        if sido_code != "36":  # 세종 is one row below: 시도 and 시 at once
            rows.append(_row(f"LG-{region}", name, "local_gov", name, "", region))
            rows.append(
                _row(f"CN-{region}", f"{name}의회", "council", name, "", region, f"LG-{region}")
            )
        rows.append(_row(f"EO-{region}", f"{name}교육청", "education_office", name, "", region))
    for code, sido_name, sg in sigungu:
        name = f"{sido_name} {sg}"
        special = SPECIAL_CITIES.get(code)
        aliases = [f"{special}특례시", f"{special}특례시청"] if special else []
        rows.append(_row(f"LG-{code}", name, "local_gov", sido_name, sg, code, "", aliases))
        if code not in NO_COUNCIL:
            council_aliases = [f"{special}특례시의회"] if special else []
            rows.append(
                _row(
                    f"CN-{code}",
                    f"{name}의회",
                    "council",
                    sido_name,
                    sg,
                    code,
                    f"LG-{code}",
                    council_aliases,
                )
            )
    return rows


def _row(
    code: str,
    name: str,
    kind: str,
    sido: str,
    sigungu: str,
    region: str,
    executive: str = "",
    aliases: list[str] | None = None,
) -> dict[str, str]:
    return {
        "code": code,
        "name": name,
        "kind": kind,
        "sido": sido,
        "sigungu": sigungu,
        "region_code": region,
        "executive_code": executive,
        "aliases": "|".join(aliases or []),
    }


def merge(curated: list[dict[str, str]], generated: list[dict[str, str]]) -> list[dict[str, str]]:
    """Curated rows win on code; their aliases are kept and generated ones added."""
    by_code = {r["code"]: dict(r) for r in generated}
    for row in curated:
        own = [a for a in row["aliases"].split("|") if a]
        base = by_code.get(row["code"])
        extra = [a for a in base["aliases"].split("|") if a] if base else []
        by_code[row["code"]] = row | {"aliases": "|".join(own + [a for a in extra if a not in own])}
    return sorted(
        by_code.values(),
        key=lambda r: (r["region_code"][:2], r["sigungu"] != "", r["region_code"],
                       KIND_ORDER[r["kind"]], r["code"]),
    )  # fmt: skip


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    curated = list(csv.DictReader(CSV_PATH.read_text(encoding="utf-8").splitlines()))
    rows = merge(curated, build(sys.argv[1]))
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    CSV_PATH.write_text(out.getvalue(), encoding="utf-8")
    print(f"{len(rows)} rows -> {CSV_PATH}")


if __name__ == "__main__":
    main()
