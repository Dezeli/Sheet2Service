"""Score stored understandings against the truth files; no model calls.

Run inside the backend container:  python manage.py shell < evaluation/score.py
It takes the latest understanding of each upload whose file name matches a truth file.
"""
import json
from pathlib import Path

from django.conf import settings

from uploads.models import Upload

SHEETS = Path(settings.BASE_DIR) / "evaluation" / "sheets"


def jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 1.0


def match_flows(found, truth):
    """Pair flows by column overlap (best first); unmatched ones count as missed or extra."""
    pairs, used = [], set()
    for t in truth:
        best = max(((jaccard(f["columns"], t["columns"]), index) for index, f in enumerate(found) if index not in used),
                   default=(0, None))
        if best[1] is not None and best[0] >= 0.3:
            used.add(best[1])
            pairs.append((t, found[best[1]], best[0]))
        else:
            pairs.append((t, None, 0))
    return pairs, [f for index, f in enumerate(found) if index not in used]


def accepts(found, expected):
    """Truth values may list defensible alternatives as 'a|b'."""
    return found in expected.split("|")


def score(understanding, truth):
    roles = understanding["columnRoles"]
    role_hits = sum(accepts(a, b) for a, b in zip(roles, truth["columnRoles"]))
    pairs, extra = match_flows(understanding["processes"], truth["processes"])
    firm = [f for f in extra if f.get("confidence") != "low"]
    lines = [f'kind {"OK" if accepts(understanding["kind"], truth["kind"]) else "MISS"} ({understanding["kind"]} / {truth["kind"]})',
             f'roles {role_hits}/{len(truth["columnRoles"])}: ' + ", ".join(
                 f"{index + 1}:{a}≠{b}" for index, (a, b) in enumerate(zip(roles, truth["columnRoles"])) if not accepts(a, b)),
             f'flows found {len(understanding["processes"])} / truth {len(truth["processes"])} '
             f'(extra {len(firm)}, tentative {len(extra) - len(firm)})']
    for t, f, overlap in pairs:
        if f is None:
            lines.append(f'  MISSED {t["title"]}')
            continue
        if t["basis"] == "status_column":
            states = jaccard([s["value"] for s in f["states"]], t["states"])
            found_transitions = {(x["from"], x["to"]) for x in f["transitions"]}
            recall = sum(tuple(x) in found_transitions for x in t["transitions"]) / len(t["transitions"])                 if t["transitions"] else 1.0
        else:
            # Stage names are the model's own words for date/flag flows; score the shape instead.
            states = 1.0 if len(f["states"]) == len(t["states"]) else 0.0
            recall = min(len(f["transitions"]) / len(t["transitions"]), 1.0) if t["transitions"] else 1.0
        after_truth = f'p{t["after"] + 1}' if "after" in t else ""
        lines.append(f'  {t["title"]} ← {f["title"]} | columns {overlap:.2f} | basis {"OK" if f["basis"] == t["basis"] else f["basis"] + "≠" + t["basis"]}'
                     f' | states {states:.2f} | transitions recall {recall:.2f} | after {"OK" if f.get("after", "") == after_truth else f.get("after", "") + "≠" + after_truth}'
                     f' | confidence {f.get("confidence", "-")}')
    for f in extra:
        lines.append(f'  {"TENTATIVE" if f.get("confidence") == "low" else "EXTRA"} {f["title"]} [{f["basis"]}] {f["columns"]}')
    return lines


for truth_path in sorted(SHEETS.glob("*.truth.json")):
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    name = truth_path.name.replace(".truth.json", ".csv")
    upload = Upload.objects.filter(original_name=name, understanding__isnull=False).order_by("-created_at").first()
    print(f"## {name}")
    if upload is None:
        print("  no stored understanding")
        continue
    print("\n".join(score(upload.understanding, truth)))
