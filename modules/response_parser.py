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
    Extract JSON từ Claude response.
    Thử nhiều strategy: raw parse → code block → first object.
    """
    raw = raw.strip()

    # Strategy 1: parse trực tiếp
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract từ ```json ... ``` hoặc ``` ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: tìm JSON object đầu tiên (greedy — handle nested)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"Không parse được JSON từ response Claude.\n"
        f"Raw (300 chars):\n{raw[:300]}"
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
