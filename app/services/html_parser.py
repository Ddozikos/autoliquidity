"""Structural parser for FSSP HTML decrees (one or more acts per file)."""
from __future__ import annotations

import re
from bs4 import BeautifulSoup, Tag

_CYRILLIC_VIN = str.maketrans({
    'А':'A','В':'B','Е':'E','К':'K','М':'M','Н':'H','О':'O','Р':'P',
    'С':'C','Т':'T','У':'Y','Х':'X','а':'A','в':'B','е':'E','к':'K',
    'м':'M','н':'H','о':'O','р':'P','с':'C','т':'T','у':'Y','х':'X',
})
_PHONETIC = dict(zip(
    'абвгдеёжзийклмнопрстуфхцчшщъыьэюя',
    ['a','b','v','g','d','e','e','zh','z','i','y','k','l','m','n','o','p','r','s','t','u','f','kh','ts','ch','sh','shch','','y','','e','yu','ya'],
))


def _text(node: Tag | BeautifulSoup) -> str:
    return re.sub(r'\s+', ' ', node.get_text(' ', strip=True)).strip()


def _first(patterns: list[str], text: str, flags: int = re.I) -> str | None:
    for pattern in patterns:
        found = re.search(pattern, text, flags)
        if found:
            return found.group(1).strip(' \t\r\n:;,')
    return None


def _number(value: str | None) -> float | None:
    if not value:
        return None
    value = value.replace('\xa0', ' ').strip()
    value = re.sub(r'[^\d,.\- ]', '', value).replace(' ', '').rstrip('.,')
    if not re.search(r'\d', value):
        return None
    # FSSP usually separates thousands with spaces and uses a dot or comma
    # followed by two kopeck digits. Keep that decimal separator only.
    if re.search(r'[,.]\d{1,2}$', value):
        sep = max(value.rfind(','), value.rfind('.'))
        fraction = value[sep+1:]
        whole = value[:sep].replace(',', '').replace('.', '')
        value = whole if set(fraction) <= {'0'} else whole + '.' + fraction
    else:
        value = value.replace(',', '').replace('.', '')
    try:
        return float(value)
    except ValueError:
        return None


def _masked(value: str | None) -> bool:
    return not value or '*' in value or 'х' in value.lower() and set(value.lower()) <= {'х'}


def _vin_candidates(text: str) -> list[tuple[str | None, str]]:
    candidates = []
    for match in re.finditer(r'\bVIN\s*[:№]?\s*([A-ZА-Я0-9*]{8,20})', text, re.I):
        raw = match.group(1).upper()
        normalized = raw.translate(_CYRILLIC_VIN)
        vin = normalized if len(normalized) == 17 and re.fullmatch(r'[A-Z0-9]{17}', normalized) else None
        candidates.append((vin, raw))
    return candidates


def _vehicle_name(paragraph: str) -> tuple[str | None, str | None]:
    before_year = re.split(r'\b\d{4}\s*г\.?\s*в\.?', paragraph, maxsplit=1, flags=re.I)[0]
    parts = [re.sub(r'\s+', ' ', part).strip() for part in before_year.split(';')]
    name = parts[2] if len(parts) >= 3 else ''
    if not name:
        name = _first([r'([А-ЯЁA-Z0-9][А-ЯЁа-яёA-Za-z0-9 ._-]{1,50}?)\s*,?\s*(?:г\s*/\s*н|VIN)'], paragraph)
    if not name:
        return None, None
    name = re.sub(r'\s+', ' ', name).strip(' ;,.')
    raw_tokens = name.split()
    if not raw_tokens:
        return None, None
    brand_words = 1
    if len(raw_tokens) > 1 and ' '.join(raw_tokens[:2]).upper() in ('АЛЬФА РОМЕО', 'ALFA ROMEO', 'LAND ROVER'):
        brand_words = 2
    brand_raw = ' '.join(raw_tokens[:brand_words])
    model_raw = ' '.join(raw_tokens[brand_words:])
    brand = _latinize_piece(brand_raw, visual=False).upper()
    brand = {'KHENDE':'HYUNDAI','KHENDAI':'HYUNDAI','HENDE':'HYUNDAI','ALFA':'ALFA'}.get(brand, brand)
    # Some FSSP vehicle names concatenate a domestic make and its numeric model.
    for prefix in ('LADA', 'VAZ', 'GAZ', 'UAZ'):
        if brand.startswith(prefix) and len(brand) > len(prefix) and brand[len(prefix)].isdigit():
            model_raw = brand[len(prefix):] + (' ' + model_raw if model_raw else '')
            brand = prefix
            break
    model = _latinize_piece(model_raw, visual=bool(re.search(r'[A-Za-z]', model_raw))).upper()
    return brand or None, model or None


def _latinize_piece(value: str, visual: bool) -> str:
    if visual:
        value = value.translate(_CYRILLIC_VIN)
    return ''.join(_PHONETIC.get(char.lower(), char) if char.lower() in _PHONETIC else char for char in value)


def _document_fields(text: str) -> dict:
    doc_date = _first([r'\bот\s+(\d{2}\.\d{2}\.\d{4})\s*№'], text)
    doc_number = _first([r'\bот\s+\d{2}\.\d{2}\.\d{4}\s*№\s*([\wА-Яа-я/-]+)'], text)
    debtor = _first([
        r'в отношении должника\s*:\s*(.+?)(?=,\s*(?:ИНН|д\.?\s*р\.?|дата рождения|адрес должника)\b)',
        r'должник\s*:\s*(.+?)(?=,\s*(?:ИНН|д\.?\s*р\.?|адрес должника)\b)',
    ], text)
    inn = _first([r'\bИНН(?:\s+должника)?\s*[:№]?\s*([0-9*]{10,12})'], text)
    debt = _first([
        r'остаток задолженности.{0,160}?составляет\s*([\d\s\u00a0.,]+\s*(?:р\.?|руб(?:лей|ля)?|₽)?)',
        r'в размере\s*:?\s*([\d\s\u00a0.,]+\s*(?:р\.?|руб(?:лей|ля)?|₽))',
    ], text)
    vzyskatel = _first([
        r'в пользу взыскателя\s*:\s*(.+?)(?=,\s*адрес взыскателя|\.\s*(?:адрес|$))',
    ], text)
    ip_id = _first([r'Идентификатор ИП\s*\(IpId\)\s*:\s*(\d+)'], text)
    ip_number = _first([r'исполнительного производства\s*№\s*([\d/]+-ИП)'], text)
    return {
        'doc_number': doc_number,
        'doc_date': doc_date,
        'debtor_name': debtor,
        'inn': None if _masked(inn) else inn,
        'debt_amount': _number(debt),
        'vzyskatel': vzyskatel,
        'ip_id': ip_id or ip_number,
    }


def _doc_type(block: Tag, text: str) -> str:
    title = ' '.join(_text(p) for p in block.find_all(['h1', 'h2', 'h3', 'p'])[:8])
    if re.search(r'о снятии запрета|отменить ранее наложенный запрет|отменить запрет', title, re.I):
        return 'removal'
    if re.search(r'постановление о запрете|объявить запрет', title, re.I):
        return 'ban'
    if re.search(r'отменить ранее наложенный запрет|постановление о снятии запрета', text, re.I):
        return 'removal'
    return 'ban'


def _parse_document(block: Tag) -> list[dict]:
    text = _text(block)
    if not text:
        return []
    fields = _document_fields(text)
    doc_type = _doc_type(block, text)

    # Vehicle rows recur in the act, the explanatory section, and the
    # resolution. Pick the richest paragraph per normalized VIN.
    best: dict[str, tuple[int, str, str | None]] = {}
    masked_rows: list[str] = []
    for paragraph in block.find_all(['p', 'div', 'td']):
        row = _text(paragraph)
        if 'VIN' not in row.upper():
            continue
        candidates = _vin_candidates(row)
        if not candidates:
            continue
        score = row.count(';') * 10 + len(row)
        for vin, raw in candidates:
            if vin:
                if vin not in best or score > best[vin][0]:
                    best[vin] = (score, row, raw)
            elif raw not in masked_rows:
                masked_rows.append(row)

    rows = list(best.values())
    if not rows and masked_rows:
        # Keep a masked vehicle in the report for manual review, but never
        # treat the mask as a VIN or as a verified vehicle identifier.
        rows = [(0, masked_rows[0], None)]
    result = []
    for _, row, raw_vin in rows:
        vin = raw_vin.translate(_CYRILLIC_VIN) if raw_vin else None
        vin = vin if vin and len(vin) == 17 and re.fullmatch(r'[A-Z0-9]{17}', vin) else None
        make, model = _vehicle_name(row)
        year = _first([r'\b(19\d{2}|20\d{2})\s*г\.?\s*в\.?'], row)
        plate = _first([r'\bг\s*/\s*н\s*([^;,.]+)'], row)
        if _masked(plate):
            plate = None
        confidence = .92 if vin else .5
        if fields['debt_amount'] is None:
            confidence *= .7
        result.append({
            **fields,
            'doc_type': doc_type,
            'vin': vin,
            'make': make,
            'model': model,
            'year': year,
            'plate': plate,
            'confidence': confidence,
        })
    return result


def parse_html(content: str | bytes) -> list[dict]:
    """Parse one FSSP HTML export, which may contain many acts and vehicles."""
    soup = BeautifulSoup(content, 'lxml')
    documents = soup.select('div#rs_act_format')
    if not documents:
        documents = [soup.body or soup]
    cars = []
    for document in documents:
        cars.extend(_parse_document(document))
    return cars
