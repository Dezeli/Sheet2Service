"""Facts about how columns move together; interpretation is left to the model.

Per-column statistics say what each column looks like. Reading a sheet's business flow needs
what rows say *jointly*: which columns are filled only after others, which dates follow which,
which small value sets split the rest. Everything here is counting over up to SAMPLE_ROWS
evenly spaced records, so a 100k-row sheet costs the same as a 5k-row one.
"""
import re
from collections import Counter, defaultdict
from datetime import date

SAMPLE_ROWS = 5_000
MAX_SET_SIZE = 12           # a status/category column rarely has more distinct values
MAX_CATEGORY_COLUMNS = 10   # bounds the conditional-missing scan
MAX_NUMERIC_COLUMNS = 15    # bounds the A±B=C triple scan
MIN_ROWS = 5
STRONG = 0.95
FLAG_PAIRS = ({"y", "n"}, {"o", "x"}, {"예", "아니오"}, {"예", "아니요"}, {"true", "false"}, {"완료", "미완료"},
              {"유", "무"}, {"있음", "없음"}, {"여", "부"}, {"v", ""}, {"o", ""}, {"✓", ""})
DATE_TEXT = re.compile(r"^(\d{4})[-./년]\s?(\d{1,2})[-./월]\s?(\d{1,2})일?(?:[ T].*)?$")
DATE_DIGITS = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
PHONE = re.compile(r"^0\d{1,2}[-. )]?\d{3,4}[-. ]?\d{4}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
URL = re.compile(r"^https?://", re.IGNORECASE)
ADDRESS = re.compile(r"(시|군|구|읍|면|동|로|길)\s?\d")


def _missing(value):
    return value is None or not str(value).strip()


def _text(value):
    return "" if value is None else str(value).strip()


def parse_date(value):
    text = _text(value)
    match = DATE_TEXT.match(text) or DATE_DIGITS.match(text)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _number(value):
    text = _text(value).replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def _sample(records):
    if len(records) <= SAMPLE_ROWS:
        return list(records)
    step = len(records) / SAMPLE_ROWS
    return [records[int(index * step)] for index in range(SAMPLE_ROWS)]


def _shape(text):
    """'M-2026-0001' -> 'A-9999-9999': identifiers share a shape, free text does not."""
    return re.sub(r"[A-Za-z가-힣]", "A", re.sub(r"\d", "9", text))[:24]


def compute_signals(records, width):
    """Return joint-column facts for the understanding prompt; empty sections are omitted."""
    rows = _sample(records)
    count = len(rows)
    if count < MIN_ROWS or width == 0:
        return {"schema_version": 1, "sampled_rows": count, "note": "표본이 적어 운영 신호를 계산하지 않았습니다."}
    cells = [[row[index] if index < len(row) else None for index in range(width)] for row in rows]
    present = [[not _missing(cell) for cell in row] for row in cells]
    presence = [sum(present[r][c] for r in range(count)) / count for c in range(width)]
    texts = [[_text(cells[r][c]) for r in range(count)] for c in range(width)]

    signals = {"schema_version": 1, "sampled_rows": count, "presence": [round(p, 3) for p in presence]}
    value_sets, flags, categories = [], [], []
    for c in range(width):
        values = Counter(texts[c][r] for r in range(count) if present[r][c])
        if not values:
            continue
        lowered = {value.lower() for value in values}
        if len(values) <= 2 and any(lowered <= pair for pair in FLAG_PAIRS):
            flags.append({"column": c + 1, "values": [{"value": v, "count": n} for v, n in values.most_common()]})
        if len(values) <= MAX_SET_SIZE and sum(values.values()) >= MIN_ROWS:
            value_sets.append({"column": c + 1, "values": [{"value": v, "count": n} for v, n in values.most_common()]})
            categories.append(c)
    if value_sets:
        signals["value_sets"] = value_sets
    if flags:
        signals["flags"] = flags

    # Conditional missing: "처리일 is empty in 97% of 접수 rows and 3% of 완료 rows".
    conditional = []
    for a in sorted(categories, key=lambda c: len(value_sets[[v["column"] for v in value_sets].index(c + 1)]["values"]))[:MAX_CATEGORY_COLUMNS]:
        by_value = defaultdict(list)
        for r in range(count):
            if present[r][a]:
                by_value[texts[a][r]].append(r)
        for b in range(width):
            if b == a or presence[b] >= 0.98 or presence[b] == 0:
                continue
            ratios = {value: round(sum(not present[r][b] for r in indexes) / len(indexes), 2)
                      for value, indexes in by_value.items() if len(indexes) >= 3}
            if ratios and max(ratios.values()) - min(ratios.values()) >= 0.5:
                conditional.append({"given": a + 1, "column": b + 1, "missing_by_value": ratios})
    if conditional:
        signals["conditional_missing"] = conditional[:60]

    # Fill chains: B present implies A present -> A is filled earlier in the row's life.
    progressive = [c for c in range(width) if 0.02 <= presence[c] <= 0.98]
    implications = []
    for b in progressive:
        rows_b = [r for r in range(count) if present[r][b]]
        for a in progressive:  # an always-filled column implies nothing about order
            if a == b or presence[a] <= presence[b]:
                continue
            ratio = sum(present[r][a] for r in rows_b) / len(rows_b)
            if ratio >= STRONG and presence[a] - presence[b] >= 0.05:
                implications.append({"earlier": a + 1, "later": b + 1, "ratio": round(ratio, 2)})
    if implications:
        signals["fill_chain"] = implications[:80]
    # Columns filled in exactly the same rows belong to one step (발주일 and 입고예정일 of a 발주).
    co_filled = []
    for i, a in enumerate(progressive):
        for b in progressive[i + 1:]:
            agree = sum(present[r][a] == present[r][b] for r in range(count)) / count
            if agree >= 0.98:
                co_filled.append({"columns": [a + 1, b + 1], "agreement": round(agree, 2)})
    if co_filled:
        signals["co_filled"] = co_filled[:40]

    # Columns that are filled progressively and imply one another form one flow candidate.
    parent = {c: c for c in progressive}

    def find(c):
        while parent[c] != c:
            parent[c] = parent[parent[c]]
            c = parent[c]
        return c
    for a, b in [(item["earlier"] - 1, item["later"] - 1) for item in implications] +             [(item["columns"][0] - 1, item["columns"][1] - 1) for item in co_filled]:
        if a in parent and b in parent:
            parent[find(a)] = find(b)
    groups = defaultdict(list)
    for c in progressive:
        groups[find(c)].append(c + 1)
    clusters = [sorted(group, key=lambda n: -presence[n - 1]) for group in groups.values() if len(group) >= 2]
    if clusters:
        signals["flow_clusters"] = sorted(clusters, key=lambda g: -len(g))[:8]

    # Dates: which precede which, and by how much.
    parsed = {}
    for c in range(width):
        values = [parse_date(cells[r][c]) if present[r][c] else None for r in range(count)]
        filled = sum(v is not None for v in values)
        if filled and filled / max(sum(present[r][c] for r in range(count)), 1) >= 0.9:
            parsed[c] = values
    date_columns = sorted(parsed)
    if date_columns:
        signals["date_columns"] = [c + 1 for c in date_columns]
    order, gaps = [], []
    for i, a in enumerate(date_columns):
        for b in date_columns[i + 1:]:
            pairs = [(parsed[a][r], parsed[b][r]) for r in range(count) if parsed[a][r] and parsed[b][r]]
            if len(pairs) < MIN_ROWS:
                continue
            before = sum(x <= y for x, y in pairs) / len(pairs)
            first, second = (a, b) if before >= 0.5 else (b, a)
            share = before if before >= 0.5 else 1 - before
            if share >= 0.9:
                order.append({"earlier": first + 1, "later": second + 1, "ratio": round(share, 2), "rows": len(pairs)})
                deltas = Counter(abs((y - x).days) for x, y in pairs)
                days, n = deltas.most_common(1)[0]
                if n / len(pairs) >= 0.3:
                    gaps.append({"earlier": first + 1, "later": second + 1, "days": days, "share": round(n / len(pairs), 2)})
    if order:
        signals["date_order"] = order[:40]
    if gaps:
        signals["date_gaps"] = gaps[:20]

    # Numbers: A - B = C / A + B = C, and running totals down the sheet.
    numeric = {}
    for c in range(width):
        values = [_number(cells[r][c]) if present[r][c] else None for r in range(count)]
        filled = sum(v is not None for v in values)
        if filled >= MIN_ROWS and filled / max(sum(present[r][c] for r in range(count)), 1) >= 0.95:
            numeric[c] = values
    numeric_columns = sorted(numeric, key=lambda c: -presence[c])[:MAX_NUMERIC_COLUMNS]
    relations = []
    for a in numeric_columns:
        for b in numeric_columns:
            if b == a:
                continue
            for c in numeric_columns:
                if c in (a, b):
                    continue
                triples = [(numeric[a][r], numeric[b][r], numeric[c][r]) for r in range(count)
                           if numeric[a][r] is not None and numeric[b][r] is not None and numeric[c][r] is not None]
                if len(triples) < MIN_ROWS:
                    continue
                for op, label in ((lambda x, y: x - y, "minus"), (lambda x, y: x + y, "plus"),
                                  (lambda x, y: x * y, "times")):
                    if label in ("plus", "times") and b < a:
                        continue  # a+b=c and a*b=c are symmetric
                    hits = sum(abs(op(x, y) - z) <= 0.01 * max(1, abs(z)) for x, y, z in triples)
                    if hits / len(triples) >= STRONG:
                        relations.append({"left": a + 1, "op": label, "right": b + 1, "equals": c + 1,
                                          "ratio": round(hits / len(triples), 2)})
    cumulative = []
    for c in numeric_columns:
        series = [v for v in numeric[c] if v is not None]
        if len(series) >= 10:
            steps = sum(y >= x for x, y in zip(series, series[1:])) / (len(series) - 1)
            if steps >= STRONG and len(set(series)) > 2:
                cumulative.append({"column": c + 1, "non_decreasing": round(steps, 2)})
    if relations:
        signals["numeric_relations"] = relations[:20]
    if cumulative:
        signals["cumulative"] = cumulative

    # Identifier and contact shapes.
    identifiers, patterns, free_text = [], [], []
    for c in range(width):
        values = [texts[c][r] for r in range(count) if present[r][c]]
        if len(values) < MIN_ROWS:
            continue
        unique = len(set(values)) / len(values)
        shapes = Counter(_shape(v) for v in values)
        shape, n = shapes.most_common(1)[0]
        if unique >= 0.98 and presence[c] >= 0.98 and n / len(values) >= 0.8 and any(ch.isdigit() for ch in shape):
            identifiers.append({"column": c + 1, "shape": shape, "shape_share": round(n / len(values), 2)})
        kinds = {"phone": PHONE, "email": EMAIL, "url": URL}
        for kind, regex in kinds.items():
            share = sum(bool(regex.search(v)) for v in values) / len(values)
            if share >= 0.8:
                patterns.append({"column": c + 1, "kind": kind, "share": round(share, 2)})
        if sum(bool(ADDRESS.search(v)) for v in values) / len(values) >= 0.8:
            patterns.append({"column": c + 1, "kind": "address", "share": round(
                sum(bool(ADDRESS.search(v)) for v in values) / len(values), 2)})
        average = sum(len(v) for v in values) / len(values)
        if average >= 20 and unique >= 0.8 and c not in parsed:
            free_text.append({"column": c + 1, "average_length": round(average)})
    if identifiers:
        signals["identifiers"] = identifiers
    if patterns:
        signals["patterns"] = patterns
    if free_text:
        signals["free_text"] = free_text

    # Which combinations of optional columns are empty together.
    optional = [c for c in range(width) if presence[c] < 0.98]
    if optional:
        combos = Counter(tuple(c + 1 for c in optional if not present[r][c]) for r in range(count))
        signals["fill_patterns"] = [{"empty_columns": list(combo), "rows": n} for combo, n in combos.most_common(5)]
    return signals
