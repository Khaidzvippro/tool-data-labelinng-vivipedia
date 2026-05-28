import json
import re

# Map normalize fact_check_status — underscore → space, typo fix
_STATUS_NORMALIZE = {
    "XAC_NHAN": "XAC NHAN",
    "MAU_THUAN": "MAU THUAN",
    "KHONG_TIM_THAY": "KHONG TIM THAY",
    "BO_QUA": "BO QUA",
    "XAC NHAN": "XAC NHAN",
    "LECH": "LECH",
    "MAU THUAN": "MAU THUAN",
    "OUTDATED": "OUTDATED",
    "KHONG TIM THAY": "KHONG TIM THAY",
    "BO QUA": "BO QUA",
}


def extract_json(raw: str) -> dict:
    """
    Extract JSON từ Claude response — chịu được text thừa trước/sau.
    Strategy theo thứ tự ưu tiên:
      1. Parse trực tiếp
      2. Lấy từ ```json ... ``` fence
      3. Tìm { bắt đầu object đến } cuối cùng (balanced brace scan)
      4. Greedy regex fallback
    """
    raw = raw.strip()

    # Strategy 1: parse trực tiếp
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strategy 2: code fence ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: balanced brace scan — tìm { đầu tiên rồi đếm brace đến khi balanced
    start = raw.find("{")
    if start != -1:
        depth = 0
        in_string = False
        escape_next = False
        for i, ch in enumerate(raw[start:], start):
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw[start:i+1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break  # nếu không parse được thì thử strategy 4

    # Strategy 4: greedy regex — lấy từ { đầu đến } cuối
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"Không parse được JSON từ response Claude.\n"
        f"Raw ({len(raw)} chars, hiện 500 đầu):\n{raw[:500]}"
    )


def normalize_data(data: dict) -> dict:
    """
    Post-process data từ Claude:
    - Normalize fact_check_status (underscore → space)
    - Clean source URLs (remove hallucinated paths nếu cần)
    """
    for claim in data.get("claims", []):
        # Normalize status
        raw_status = str(claim.get("fact_check_status", "")).strip().upper()
        claim["fact_check_status"] = _STATUS_NORMALIZE.get(raw_status, raw_status)

        # Ensure numeric fields are float
        for field in ["source_fidelity", "source_coverage", "hallucination_rate", "source_quality"]:
            val = claim.get(field, 0)
            try:
                claim[field] = float(val)
            except (TypeError, ValueError):
                claim[field] = 0.0

    # Article level float fields
    art = data.get("article", {})
    for field in ["rel", "comp"]:
        val = art.get(field, 0)
        try:
            art[field] = float(val)
        except (TypeError, ValueError):
            art[field] = 0.0

    return data


def validate_schema(data: dict) -> bool:
    """Kiểm tra schema tối thiểu theo rule.md."""
    return "article" in data and "claims" in data
