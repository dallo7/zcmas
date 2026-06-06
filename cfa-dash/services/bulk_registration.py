from __future__ import annotations

import base64
import csv
import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree


EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)

FIELD_ALIASES = {
    "company_name": {"company", "company name", "cfa", "cfa name", "clearing agent", "organisation", "organization"},
    "first_name": {"first", "first name", "firstname", "contact first name", "admin first name"},
    "last_name": {"last", "last name", "lastname", "surname", "contact last name", "admin last name"},
    "contact_name": {"name", "contact", "contact person", "admin", "administrator", "full name"},
    "email": {"email", "email address", "company email", "admin email", "contact email"},
    "phone": {"phone", "telephone", "mobile", "contact phone", "company phone"},
    "whatsapp": {"whatsapp", "whatsapp number"},
    "pacra_number": {"pacra", "pacra number", "registration number"},
    "tpin": {"tpin", "tin", "tax number", "taxpayer number"},
    "zra_licence": {"zra licence", "zra license", "zra", "customs licence", "customs license"},
    "zaffa_number": {"zaffa", "zaffa number", "membership number"},
}


def parse_bulk_registration_upload(filename: str, contents: str) -> list[dict]:
    """Parse uploaded CFA bulk-registration data into normalized records."""
    file_name = filename or "bulk-registration.txt"
    raw = _decode_dash_upload(contents)
    suffix = Path(file_name).suffix.lower()
    if suffix in {".csv", ".txt"}:
        text = raw.decode("utf-8-sig", errors="replace")
        rows = _records_from_delimited_text(text) or _records_from_free_text(text)
    elif suffix == ".xlsx":
        rows = _records_from_xlsx(raw)
    elif suffix == ".docx":
        rows = _records_from_free_text(_docx_text(raw))
    elif suffix == ".doc":
        rows = _records_from_free_text(_binary_text(raw))
    elif suffix == ".pdf":
        rows = _records_from_free_text(_pdf_text(raw))
    elif suffix == ".xls":
        rows = _records_from_free_text(_binary_text(raw))
    else:
        raise ValueError("Upload a CSV, TXT, XLSX, DOCX, or PDF file.")
    normalized = [_normalize_record(row) for row in rows]
    normalized = [row for row in normalized if row.get("email")]
    if not normalized:
        raise ValueError("No valid CFA email addresses were found in the uploaded file.")
    return _dedupe_by_email(normalized)


def _decode_dash_upload(contents: str) -> bytes:
    if not contents or "," not in contents:
        raise ValueError("Upload file content was empty or invalid.")
    return base64.b64decode(contents.split(",", 1)[1])


def _records_from_delimited_text(text: str) -> list[dict]:
    sample = text.strip()
    if not sample:
        return []
    try:
        dialect = csv.Sniffer().sniff(sample[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames or not any(_canonical_field(field or "") for field in reader.fieldnames or []):
        return []
    return [dict(row) for row in reader if any((value or "").strip() for value in row.values())]


def _records_from_xlsx(raw: bytes) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        shared_strings = _xlsx_shared_strings(archive)
        sheet_name = _xlsx_first_sheet_name(archive)
        root = ElementTree.fromstring(archive.read(sheet_name))
    rows = []
    for row in root.findall(".//{*}sheetData/{*}row"):
        values = [_xlsx_cell_value(cell, shared_strings) for cell in row.findall("{*}c")]
        if any(value.strip() for value in values):
            rows.append(values)
    if len(rows) < 2:
        return []
    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:] if any(value.strip() for value in row)]


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.itertext()) for node in root.findall("{*}si")]


def _xlsx_first_sheet_name(archive: zipfile.ZipFile) -> str:
    try:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        first_sheet = workbook.find(".//{*}sheet")
        rel_id = first_sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id") if first_sheet is not None else None
        for rel in rels.findall("{*}Relationship"):
            if rel.attrib.get("Id") == rel_id:
                target = rel.attrib["Target"].lstrip("/")
                return target if target.startswith("xl/") else "xl/" + target
    except Exception:
        pass
    return "xl/worksheets/sheet1.xml"


def _xlsx_cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    value = cell.find("{*}v")
    text = value.text if value is not None and value.text is not None else ""
    if cell.attrib.get("t") == "s" and text.isdigit():
        index = int(text)
        return shared_strings[index] if index < len(shared_strings) else ""
    if cell.attrib.get("t") == "inlineStr":
        inline = cell.find("{*}is")
        return "".join(inline.itertext()) if inline is not None else ""
    return text


def _docx_text(raw: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    paragraphs = []
    for para in root.findall(".//{*}p"):
        text = "".join(para.itertext()).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _pdf_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Could not read PDF text: {exc}") from exc


def _binary_text(raw: bytes) -> str:
    text = raw.decode("latin-1", errors="ignore")
    return re.sub(r"[^\x09\x0A\x0D\x20-\x7E]+", " ", text)


def _records_from_free_text(text: str) -> list[dict]:
    records = []
    for line in text.splitlines():
        emails = EMAIL_RE.findall(line)
        for email in emails:
            company = line.replace(email, " ")
            company = re.sub(r"[\s,;|:-]+", " ", company).strip()
            records.append({"company_name": company, "email": email})
    return records


def _normalize_record(row: dict) -> dict:
    mapped: dict[str, str] = {}
    for key, value in row.items():
        canonical = _canonical_field(key or "")
        if canonical:
            mapped[canonical] = str(value or "").strip()
    if not mapped.get("email"):
        match = EMAIL_RE.search(" ".join(str(value or "") for value in row.values()))
        if match:
            mapped["email"] = match.group(0).strip()
    contact_name = mapped.get("contact_name") or ""
    first, last = _split_name(contact_name, mapped.get("email", ""))
    mapped["first_name"] = mapped.get("first_name") or first
    mapped["last_name"] = mapped.get("last_name") or last
    mapped["company_name"] = mapped.get("company_name") or _company_name_from_email(mapped.get("email", ""))
    mapped["username"] = _username_from_email(mapped.get("email", ""))
    mapped["company_email"] = mapped.get("email", "")
    return mapped


def _canonical_field(label: str) -> str | None:
    normalized = re.sub(r"[_\-/]+", " ", label.strip().lower())
    normalized = re.sub(r"\s+", " ", normalized)
    for canonical, aliases in FIELD_ALIASES.items():
        if normalized in aliases:
            return canonical
    return None


def _split_name(name: str, email: str) -> tuple[str, str]:
    parts = [part for part in re.split(r"\s+", name.strip()) if part]
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    if len(parts) == 1:
        return parts[0], "Admin"
    local = (email.split("@", 1)[0] if email else "cfa.admin").replace(".", " ").replace("_", " ")
    local_parts = [part.title() for part in local.split() if part]
    if len(local_parts) >= 2:
        return local_parts[0], " ".join(local_parts[1:])
    return (local_parts[0] if local_parts else "CFA"), "Admin"


def _company_name_from_email(email: str) -> str:
    domain = (email.split("@", 1)[1] if "@" in email else "cfa").split(".", 1)[0]
    words = [word for word in re.split(r"[^a-zA-Z0-9]+", domain) if word]
    return " ".join(word.capitalize() for word in words) or "CFA Company"


def _username_from_email(email: str) -> str:
    # Bulk files often contain repeated local-parts across different domains.
    # Using the full email preserves uniqueness while still allowing email login.
    return email.strip().lower() if email else "cfa"


def _dedupe_by_email(records: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for record in records:
        email = record.get("email", "").lower()
        if email and email not in seen:
            seen.add(email)
            unique.append(record)
    return unique
