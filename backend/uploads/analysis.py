"""Deterministic profiling; original values are never cast or rewritten."""
import csv
import hashlib
import io
import random
import re
from collections import Counter
from datetime import date, datetime, time

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50_000
MAX_COLUMNS = 200
MAX_CELLS = 500_000
INFERENCE_SAMPLE_LIMIT = 10
csv.field_size_limit(100_000)


class TableError(ValueError):
    pass


def missing(value):
    return value is None or (isinstance(value, str) and not value.strip())


def serial(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def csv_text(data, encoding, allow_replacement=False):
    if encoding not in ("auto", "utf-8-sig", "euc-kr", "cp949"):
        raise TableError("지원하지 않는 인코딩입니다.")
    candidates = ("utf-8-sig", "cp949") if encoding == "auto" else (encoding,)
    for candidate in candidates:
        try:
            return data.decode(candidate), candidate, 0
        except UnicodeDecodeError:
            continue
    if encoding == "auto":
        # Only recover sparse errors. Use non-ASCII bytes as the denominator so
        # a large ASCII table cannot hide badly decoded non-ASCII content.
        recovery_candidates = ("utf-8-sig",) if data.startswith(b'\xef\xbb\xbf') else candidates
        options = []
        for candidate in recovery_candidates:
            text = data.decode(candidate, errors="surrogateescape")
            count = sum(0xDC80 <= ord(char) <= 0xDCFF for char in text)
            options.append((count, candidate, text))
        count, candidate, text = min(options, key=lambda item: item[0])
        non_ascii = sum(byte >= 128 for byte in data)
        if count / max(non_ascii, 1) <= 0.001:
            return ''.join('\ufffd' if 0xDC80 <= ord(char) <= 0xDCFF else char for char in text), candidate, count
    if allow_replacement:
        if encoding == "auto":
            raise TableError("문자 대체를 사용하려면 UTF-8, EUC-KR 또는 CP949를 직접 선택해 주세요.")
        # Surrogate escapes identify undecodable bytes without counting literal U+FFFD.
        text = data.decode(encoding, errors="surrogateescape")
        count = sum(0xDC80 <= ord(char) <= 0xDCFF for char in text)
        text = ''.join('\ufffd' if 0xDC80 <= ord(char) <= 0xDCFF else char for char in text)
        return text, encoding, count
    raise TableError("파일의 문자 인코딩을 확실하게 읽지 못했습니다. Excel에서 CSV UTF-8로 다시 저장하거나 고급 설정을 확인해 주세요.")


def analyze(data, encoding="auto", allow_replacement=False):
    try:
        text, actual_encoding, replaced = csv_text(data, encoding, allow_replacement)
        if "\x00" in text:
            raise TableError("CSV에 지원하지 않는 NUL 문자가 있습니다. UTF-8 CSV로 다시 저장해 주세요.")
        rows = csv.reader(io.StringIO(text, newline=""), strict=True)
        report = profile(rows, sample_seed=int.from_bytes(hashlib.sha256(data).digest()[:8], "big"))
        report["source"] = {"format": "csv", "encoding": actual_encoding, "delimiter": ",", "replaced_bytes": replaced}
        if replaced:
            report["warnings"].insert(0, f"읽을 수 없는 바이트 {replaced}개를 �로 표시했습니다. 해당 값의 통계·고유값은 정확하지 않을 수 있습니다. 원본 파일은 변경하지 않았습니다.")
        return report
    except TableError:
        raise
    except (csv.Error, ValueError, TypeError) as exc:
        raise TableError("표를 읽지 못했습니다. 파일 형식과 셀 값을 확인해 주세요.") from exc


def read_page(data, *, encoding, width, page, page_size=20):
    """Read one page of nonblank CSV records without changing saved analysis."""
    text, _, _ = csv_text(data, encoding, allow_replacement=True)
    rows = csv.reader(io.StringIO(text, newline=""), strict=True)
    next(rows, None)
    start = (page - 1) * page_size
    stop = start + page_size
    result = []
    record_index = 0
    for row_number, row in enumerate(rows, start=2):
        if all(missing(value) for value in row):
            continue
        if record_index >= stop:
            break
        if record_index >= start:
            result.append({"row_number": row_number,
                           "values": [serial(row[index]) if index < len(row) else None
                                      for index in range(width)]})
        record_index += 1
    return result


def chart_counts(data, *, encoding, column_numbers):
    """Count chart categories across all nonblank CSV records."""
    text, _, _ = csv_text(data, encoding, allow_replacement=True)
    rows = csv.reader(io.StringIO(text, newline=""), strict=True)
    next(rows, None)
    counts = {number: Counter() for number in column_numbers}
    total = 0
    for row in rows:
        if all(missing(value) for value in row):
            continue
        total += 1
        for number in column_numbers:
            value = row[number - 1] if number <= len(row) else None
            counts[number][None if missing(value) else value] += 1
    result = {}
    for number, categories in counts.items():
        sorted_groups = sorted(categories.items(), key=lambda item: item[1], reverse=True)
        if len(sorted_groups) > 8:
            visible = sorted_groups[:7]
            remainder = sorted_groups[7:]
            visible.append((f"나머지 {len(remainder)}개 분류", sum(count for _, count in remainder)))
        else:
            visible = sorted_groups
        result[f"column_{number}"] = {
            "total": total,
            "groups": [{"label": "값 없음" if label is None else label, "count": count,
                        "ratio": count / total if total else 0} for label, count in visible],
        }
    return result


def value_kind(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, datetime):
        return "datetime"
    if isinstance(value, date):
        return "date"
    if isinstance(value, time):
        return "time"
    if isinstance(value, (int, float)):
        return "number"
    text = str(value).strip()
    if text.startswith("="):
        return "formula"
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?", text):
        return "number"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[ T].+)?", text):
        try:
            datetime.fromisoformat(text)
            return "datetime" if len(text) > 10 else "date"
        except ValueError:
            pass
    if re.fullmatch(r"\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?", text):
        try:
            time.fromisoformat(text)
            return "time"
        except ValueError:
            pass
    return "text"


def profile(rows, *, sample_seed=0):
    header = list(next(rows, []))
    if not header:
        raise TableError("첫 행에 컬럼명이 있는 표가 필요합니다.")
    records = []
    row_numbers = []
    width = len(header)
    skipped = 0
    for line, row in enumerate(rows, start=2):
        if line > MAX_ROWS + 1:
            raise TableError("한 번에 최대 50,000개 데이터 행을 분석할 수 있습니다.")
        row = list(row)
        width = max(width, len(row))
        if width > MAX_COLUMNS or width * (len(records) + 1) > MAX_CELLS:
            raise TableError("표는 최대 200열, 500,000셀까지 지원합니다.")
        if all(missing(value) for value in row):
            skipped += 1
            continue
        records.append(row)
        row_numbers.append(line)
    if width > MAX_COLUMNS:
        raise TableError("표는 최대 200열까지 지원합니다.")
    if all(missing(value) for value in header) and not records:
        raise TableError("표에 컬럼명이나 데이터가 없습니다.")
    warnings = []
    if skipped:
        warnings.append(f"완전히 빈 데이터 행 {skipped}개는 통계에서 제외했습니다. 원본 파일에는 유지됩니다.")
    if len(records) < 5:
        warnings.append("표본이 5행 미만입니다. 타입 후보와 고유성은 추가 데이터에서 달라질 수 있습니다.")
    if any(len(row) != len(header) for row in records):
        warnings.append("행마다 컬럼 수가 다릅니다. 부족한 위치는 빈 값으로 표시하고 추가 컬럼도 보존했습니다.")
    names = [str(serial(header[i])) if i < len(header) and not missing(header[i]) else "" for i in range(width)]
    counts = Counter(name.strip() for name in names if name.strip())
    columns = []
    for index, name in enumerate(names):
        values = [row[index] if index < len(row) else None for row in records]
        present = [value for value in values if not missing(value)]
        kinds = Counter(value_kind(value) for value in present)
        issues = []
        if not name:
            issues.append("컬럼명이 비어 있어 임시 이름을 표시합니다.")
        elif counts[name.strip()] > 1:
            issues.append("중복 컬럼명입니다. 위치별 ID로 구분하며 값을 합치지 않습니다.")
        if len(kinds) > 1:
            issues.append("여러 값 형식이 섞여 있습니다.")
        leading_zero = any(isinstance(v, str) and re.fullmatch(r"[+-]?0\d+", v.strip()) for v in present)
        if leading_zero:
            issues.append("앞자리 0이 있는 숫자 문자열입니다. 식별자일 수 있어 텍스트 후보로 유지합니다.")
        if kinds["formula"]:
            issues.append("수식은 실행하지 않고 수식 문자열로 표시합니다.")
        candidate = next(iter(kinds)) if len(kinds) == 1 else "mixed" if kinds else "unknown"
        if leading_zero and candidate == "number":
            candidate = "text"
        unique = len({(type(v).__name__, str(v)) for v in present})
        denominator = len(present)
        columns.append({
            "id": f"column_{index + 1}", "name": name, "label": name or f"컬럼 {index + 1}",
            "candidate": candidate, "non_empty_count": denominator,
            "missing_count": len(values) - denominator,
            "missing_ratio": (len(values) - denominator) / len(values) if values else 0,
            "unique_count": unique, "type_counts": dict(kinds),
            "number_ratio": kinds["number"] / denominator if denominator else 0,
            "date_ratio": (kinds["date"] + kinds["datetime"]) / denominator if denominator else 0,
            "issues": issues,
        })
    if len(records) <= INFERENCE_SAMPLE_LIMIT:
        sample_indexes = list(range(len(records)))
    else:
        count = len(records)
        fixed = {0, 1, (count - 1) // 2, (count + 1) // 2, count - 2, count - 1}
        remaining = [index for index in range(count) if index not in fixed]
        rng = random.Random(sample_seed)
        random_indexes = []
        for part in range(4):
            segment = remaining[part * len(remaining) // 4:(part + 1) * len(remaining) // 4]
            inset = len(segment) // 4
            interior = segment[inset:len(segment) - inset] or segment
            random_indexes.append(rng.choice(interior))
        sample_indexes = sorted(fixed.union(random_indexes))

    def report_row(index):
        row = records[index]
        return {"row_number": row_numbers[index],
                "values": [serial(row[i]) if i < len(row) else None for i in range(width)]}

    return {
        "schema_version": 1, "row_count": len(records), "column_count": width,
        "skipped_blank_rows": skipped, "columns": columns, "warnings": warnings,
        "preview": [report_row(index) for index in range(min(20, len(records)))],
        "preview_limit": 20,
        "inference_samples": [report_row(index) for index in sample_indexes],
    }
