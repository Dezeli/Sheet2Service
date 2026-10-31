"""The analysis payload sent to Claude: an explicit allowlist of column statistics and sample rows."""
import copy
import json

MAX_INPUT_BYTES = 64_000
MAX_SAMPLE_ROWS = 10
MAX_TEXT_CHARS = 160


class AnalysisInputError(ValueError):
    pass


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _clip(value, path, truncated):
    if isinstance(value, str) and len(value) > MAX_TEXT_CHARS:
        truncated.append(path)
        return value[:MAX_TEXT_CHARS]
    return value


def build_input(report):
    """Use an explicit allowlist; never send the raw file or upload metadata."""
    if report.get("schema_version") != 1:
        raise AnalysisInputError("지원하지 않는 분석 버전입니다.")
    columns = report["columns"]
    samples = report.get("inference_samples")
    if not isinstance(samples, list) or len(samples) > MAX_SAMPLE_ROWS:
        raise AnalysisInputError("요청에 필요한 예시 행이 없습니다. CSV를 다시 분석하거나 업로드해 주세요.")
    truncated = []
    allowed = ("name", "candidate", "non_empty_count", "missing_count",
               "unique_count", "type_counts", "number_ratio", "date_ratio", "issues")
    supplied_columns = []
    for number, column in enumerate(columns, 1):
        item = {"number": number}
        for key in allowed:
            value = copy.deepcopy(column[key])
            if key == "name":
                value = _clip(value, f"columns.{number}.name", truncated)
            elif key == "issues":
                value = [_clip(issue, f"columns.{number}.issues.{index}", truncated)
                         for index, issue in enumerate(value)]
            item[key] = value
        supplied_columns.append(item)
    sample_rows = []
    for row in samples:
        if len(row["values"]) != len(columns):
            raise AnalysisInputError("예시 행과 컬럼 수가 다릅니다.")
        sample_rows.append({"row_number": row["row_number"],
                            "values": [_clip(value, f'sample_rows.{row["row_number"]}.{number}', truncated)
                                       for number, value in enumerate(row["values"], 1)]})
    result = {"row_count": report["row_count"], "columns": supplied_columns,
              "warnings": [_clip(value, f"warnings.{index}", truncated)
                           for index, value in enumerate(report["warnings"])],
              "sample_rows": sample_rows,
              "sampling": {"strategy": "first_2_middle_2_last_2_and_4_seeded_stratified_random_nonblank_rows",
                           "max_rows": MAX_SAMPLE_ROWS, "max_text_chars": MAX_TEXT_CHARS,
                           "truncated_paths": truncated, "representative": False}}
    if len(_json(result).encode("utf-8")) > MAX_INPUT_BYTES:
        raise AnalysisInputError("분석 입력이 64,000바이트를 초과했습니다.")
    return result
