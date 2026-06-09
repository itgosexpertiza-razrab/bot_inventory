import re
from decimal import Decimal, InvalidOperation



def norm_text(s: str) -> str:
    return (s or "").strip()

def norm_cabinet(user_input: str) -> str:
    s = norm_text(user_input).lower()

    # цифры
    if re.fullmatch(r"\d{1,4}", s):
        return s

    # исключения
    if "сервер" in s:
        return "СЕРВЕРНАЯ"
    if "конференц" in s:
        return "КОНФЕРЕНЦ-ЗАЛ"
    if "актов" in s:
        return "АКТОВЫЙ ЗАЛ"

    # если ввели что-то ещё — вернем как есть (верхний регистр)
    return norm_text(user_input).upper()

def cab_match(db_value: str, query_value: str) -> bool:
    """Сопоставление кабинета из справочника с запросом пользователя."""
    q = norm_cabinet(query_value)

    v_raw = (db_value or "").strip()
    v_low = v_raw.lower()

    # если запрос цифры — сравниваем как строку цифр
    if re.fullmatch(r"\d{1,4}", q.lower()):
        return v_raw.strip() == q

    # исключения: серверная/конференц/актовый
    if q == "СЕРВЕРНАЯ":
        return "сервер" in v_low
    if q == "КОНФЕРЕНЦ-ЗАЛ":
        return "конференц" in v_low
    if q == "АКТОВЫЙ ЗАЛ":
        return "актов" in v_low

    return v_raw.upper() == q


def norm_inv(s: str) -> str:
    if s is None:
        return ""

    if isinstance(s, float) and s.is_integer():
        s = str(int(s))
    elif isinstance(s, Decimal):
        try:
            s = str(int(s)) if s == s.to_integral_value() else format(s, "f")
        except (InvalidOperation, ValueError):
            s = str(s)
    else:
        s = str(s)

    s = s.strip()
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".", 1)[0]

    # оставляем только цифры
    digits = re.sub(r"\D+", "", s)

    if not digits:
        return ""
    # если до 6 цифр — дополняем нулями слева
    if len(digits) <= 6:
        return digits.zfill(6)
    return digits


def inv_candidates_from_barcode(raw: str) -> list[str]:
    """
    Возвращает список возможных инвентарных номеров (6 цифр),
    извлечённых из распознанного штрихкода/текста.
    """
    s = "" if raw is None else str(raw).strip()
    digits = re.sub(r"\D+", "", s)
    if not digits:
        return []

    cands = []

    # 1) если ровно 6 цифр — это уже инв
    if len(digits) == 6:
        cands.append(digits)

    # 2) если больше 6 — берём:
    #    - последние 6
    #    - последние 7 без контрольной (если EAN-13/похожие)
    if len(digits) > 6:
        cands.append(digits[-6:])


    if len(digits) >= 7:
        cands.append(digits[-7:-1])  # 6 цифр перед последней (контрольной)

    # 3) все 6-значные подстроки (на случай префиксов)
    for i in range(0, len(digits) - 5):
        cands.append(digits[i:i+6])

    # уникализируем, сохраняя порядок
    seen = set()
    out = []
    for x in cands:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

