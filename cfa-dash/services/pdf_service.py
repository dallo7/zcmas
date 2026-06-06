from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from services.db import DATA_DIR


def _gn83_total(invoice: dict) -> float:
    """Invoice amount due — prefers stored GN83 total, then payable, then fee components."""
    total = float(invoice.get("total") or 0)
    if total > 0:
        return total
    payable = float(invoice.get("payable_amount") or invoice.get("payment_amount") or 0)
    if payable > 0:
        return payable
    admin = float(invoice.get("admin_fee") or 0)
    vat = float(invoice.get("vat") or 0)
    if admin or vat:
        return float(math.ceil(admin + vat - 1e-9))
    return 0.0


def _capitalpay_checkout(invoice: dict) -> float | None:
    gn83 = _gn83_total(invoice)
    payable = float(invoice.get("payable_amount") or invoice.get("payment_amount") or gn83)
    if payable > gn83 + 0.001:
        return payable
    return None


def _zcams_checkout_link(invoice: dict) -> str | None:
    invoice_id = invoice.get("id")
    if not invoice_id:
        return None
    base = (os.getenv("PUBLIC_APP_URL") or "http://127.0.0.1:8050").strip().rstrip("/")
    return f"{base}/capitalpay/checkout/{invoice_id}"


INVOICE_PDF_DIR = DATA_DIR / "invoices"
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
INVOICE_LOGO_PATH = ASSETS_DIR / "zcams-logo.png"
CAPITALPAY_LOGO_PATH = ASSETS_DIR / "capitalPay.png"

# Authorised collection banks — logo PNGs in assets/.
AUTHORISED_COLLECTION_BANK_LOGOS: list[Path] = [
    ASSETS_DIR / "Zanaco.png",
    ASSETS_DIR / "Stanbic.png",
    ASSETS_DIR / "FNB Bank.png",
    ASSETS_DIR / "ABSA.png",
    ASSETS_DIR / "Standard Zambia.png",
]

# Invoice PDF colour palette (aligned with ZCAMS theme).
COLOR_ZCAMS_GREEN = colors.HexColor("#06451F")
COLOR_ZCAMS_GREEN_DARK = colors.HexColor("#063619")
COLOR_MINT_BG = colors.HexColor("#EAF6EC")
COLOR_PANEL_BG = colors.HexColor("#FBFEFB")
COLOR_BANK_BORDER = colors.HexColor("#06451F")
COLOR_BANK_BG = colors.HexColor("#F2FAF4")
COLOR_CPAY_BLUE = colors.HexColor("#0033A0")
COLOR_CPAY_BG = colors.HexColor("#E8F0FA")
COLOR_IMPORTER_GREEN = colors.HexColor("#2D6A4E")
COLOR_IMPORTER_BG = colors.HexColor("#EDF6F0")
COLOR_GRID_LINE = colors.HexColor("#CFE3D4")


def invoice_pdf_path(invoice_id: str, invoice_number: str) -> Path:
    INVOICE_PDF_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in invoice_number)
    return INVOICE_PDF_DIR / f"{invoice_id}_{safe}.pdf"


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "InvTitle",
            parent=base["Heading1"],
            fontSize=20,
            textColor=colors.HexColor("#0B3D2E"),
            spaceAfter=4,
            fontName="Helvetica-Bold",
        ),
        "subtitle": ParagraphStyle(
            "InvSub",
            parent=base["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#4A5D52"),
            spaceAfter=2,
        ),
        "label": ParagraphStyle(
            "InvLabel",
            parent=base["Normal"],
            fontSize=7.8,
            leading=9,
            textColor=COLOR_ZCAMS_GREEN,
            fontName="Helvetica-Bold",
        ),
        "value": ParagraphStyle(
            "InvValue",
            parent=base["Normal"],
            fontSize=10.2,
            leading=12.5,
            textColor=colors.HexColor("#1A2E24"),
            spaceAfter=6,
        ),
        "total": ParagraphStyle(
            "InvTotal",
            parent=base["Heading2"],
            fontSize=18,
            textColor=colors.HexColor("#0B3D2E"),
            alignment=TA_RIGHT,
            fontName="Helvetica-Bold",
        ),
        "label_on_green": ParagraphStyle(
            "InvLabelOnGreen",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.white,
            fontName="Helvetica-Bold",
        ),
        "total_on_green": ParagraphStyle(
            "InvTotalOnGreen",
            parent=base["Heading2"],
            fontSize=19,
            leading=23,
            textColor=colors.white,
            alignment=TA_RIGHT,
            fontName="Helvetica-Bold",
        ),
        "footer": ParagraphStyle(
            "InvFooter",
            parent=base["Normal"],
            fontSize=8,
            textColor=colors.HexColor("#6B7C72"),
            alignment=TA_CENTER,
        ),
        "cpay_label": ParagraphStyle(
            "InvCpayLabel",
            parent=base["Normal"],
            fontSize=10.5,
            textColor=COLOR_ZCAMS_GREEN_DARK,
            alignment=TA_CENTER,
            spaceAfter=6,
            fontName="Helvetica-Bold",
        ),
        "cpay_ref": ParagraphStyle(
            "InvCpayRef",
            parent=base["Heading1"],
            fontSize=18,
            textColor=COLOR_CPAY_BLUE,
            alignment=TA_CENTER,
            spaceAfter=4,
            fontName="Helvetica-Bold",
            leading=22,
        ),
        "section_banks": ParagraphStyle(
            "InvSectionBanks",
            parent=base["Normal"],
            fontSize=8.4,
            textColor=colors.white,
            fontName="Helvetica-Bold",
            spaceAfter=2,
        ),
        "section_header": ParagraphStyle(
            "InvSectionHeader",
            parent=base["Normal"],
            fontSize=8.4,
            leading=10,
            textColor=colors.white,
            fontName="Helvetica-Bold",
        ),
        "section_importer": ParagraphStyle(
            "InvSectionImporter",
            parent=base["Normal"],
            fontSize=8,
            textColor=COLOR_IMPORTER_GREEN,
            fontName="Helvetica-Bold",
            spaceAfter=2,
        ),
        "cpay_value": ParagraphStyle(
            "InvCpayValue",
            parent=base["Normal"],
            fontSize=10,
            textColor=COLOR_CPAY_BLUE,
            fontName="Helvetica-Bold",
            spaceAfter=6,
        ),
        "cpay_label_row": ParagraphStyle(
            "InvCpayLabelRow",
            parent=base["Normal"],
            fontSize=8,
            textColor=COLOR_CPAY_BLUE,
            fontName="Helvetica-Bold",
        ),
        "center_sub": ParagraphStyle(
            "InvCenterSub",
            parent=base["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#4A5D52"),
            alignment=TA_CENTER,
            spaceAfter=2,
        ),
        "notice_title": ParagraphStyle(
            "NoticeTitle",
            parent=base["Heading1"],
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#0B3D2E"),
            fontName="Helvetica-Bold",
            spaceAfter=2,
        ),
        "notice_subtitle": ParagraphStyle(
            "NoticeSubtitle",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#4A5D52"),
            fontName="Helvetica",
        ),
        "tiny_caps": ParagraphStyle(
            "TinyCaps",
            parent=base["Normal"],
            fontSize=7.5,
            leading=9,
            textColor=colors.HexColor("#6B7C72"),
            fontName="Helvetica-Bold",
        ),
        "notice_value": ParagraphStyle(
            "NoticeValue",
            parent=base["Normal"],
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#172515"),
            fontName="Helvetica-Bold",
            spaceAfter=4,
        ),
        "notice_amount": ParagraphStyle(
            "NoticeAmount",
            parent=base["Heading1"],
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#0B3D2E"),
            fontName="Helvetica-Bold",
            alignment=TA_RIGHT,
        ),
        "bank_name": ParagraphStyle(
            "BankName",
            parent=base["Normal"],
            fontSize=9,
            leading=11,
            textColor=colors.HexColor("#172515"),
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        ),
        "bank_detail": ParagraphStyle(
            "BankDetail",
            parent=base["Normal"],
            fontSize=7,
            leading=8.5,
            textColor=colors.HexColor("#4A5D52"),
            alignment=TA_CENTER,
        ),
        "instruction": ParagraphStyle(
            "PaymentInstruction",
            parent=base["Normal"],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#263522"),
        ),
        "stamp": ParagraphStyle(
            "CertifiedStamp",
            parent=base["Heading1"],
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#0B3D2E"),
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        ),
    }


def _invoice_logo_image(max_width: float = 7.0 * cm) -> Image | None:
    if not INVOICE_LOGO_PATH.is_file():
        return None
    img = Image(str(INVOICE_LOGO_PATH))
    ratio = img.imageHeight / float(img.imageWidth)
    img.drawWidth = max_width
    img.drawHeight = max_width * ratio
    img.hAlign = "CENTER"
    return img


def _capitalpay_logo(max_width: float = 1.1 * cm, max_height: float = 1.1 * cm) -> Image | Paragraph:
    if CAPITALPAY_LOGO_PATH.is_file():
        return _scaled_image(CAPITALPAY_LOGO_PATH, max_width, max_height)
    return Paragraph("Payment Gateway", _styles()["instruction"])


def _company_logo_path(company: dict) -> Path | None:
    logo_path = (company or {}).get("logo_path")
    if not logo_path:
        return None
    path = (DATA_DIR.parent / logo_path).resolve()
    uploads_root = (DATA_DIR.parent / "uploads").resolve()
    if uploads_root not in path.parents or not path.is_file():
        return None
    return path


def _footer_company_logo(company: dict):
    logo_path = _company_logo_path(company)
    company_name = str((company or {}).get("name") or "Clearing & Forwarding Agent")
    company_email = str((company or {}).get("company_email") or "")
    company_phone = str((company or {}).get("phone") or "")

    def draw(canvas, _doc):
        if not logo_path:
            return
        try:
            image = ImageReader(str(logo_path))
            canvas.saveState()
            size = 18 * mm
            right_x = A4[0] - 1.5 * cm
            logo_x = right_x - size
            logo_y = 8 * mm
            canvas.drawImage(
                image,
                logo_x,
                logo_y,
                width=size,
                height=size,
                preserveAspectRatio=True,
                mask="auto",
            )
            text_x = logo_x - 3 * mm
            text_y = logo_y + size - 2 * mm
            canvas.setFillColor(colors.HexColor("#1A2E24"))
            canvas.setFont("Helvetica-Bold", 7)
            canvas.drawRightString(text_x, text_y, company_name[:42])
            canvas.setFillColor(colors.HexColor("#4A5D52"))
            canvas.setFont("Helvetica", 6)
            if company_email:
                text_y -= 3.2 * mm
                canvas.drawRightString(text_x, text_y, company_email[:48])
            if company_phone:
                text_y -= 3.2 * mm
                canvas.drawRightString(text_x, text_y, f"Tel: {company_phone}"[:48])
            canvas.restoreState()
        except Exception:
            return

    return draw


def _centered_block(flowables: list[Any]) -> Table:
    """Wrap flowables in a full-width table cell for horizontal centering."""
    table = Table([[flowables]], colWidths=[16.5 * cm])
    table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _scaled_image(path: Path, max_width: float, max_height: float) -> Image:
    img = Image(str(path))
    scale = min(max_width / float(img.imageWidth), max_height / float(img.imageHeight))
    img.drawWidth = float(img.imageWidth) * scale
    img.drawHeight = float(img.imageHeight) * scale
    img.hAlign = "CENTER"
    return img


def _bank_logo_card(
    path: Path,
    *,
    rule: Any,
    bank_bg: Any,
    max_logo_w: float,
    max_logo_h: float,
) -> Table:
    card = Table([[_bank_logo_cell(path, max_logo_w, max_logo_h)]], colWidths=[None])
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bank_bg),
                ("BOX", (0, 0), (-1, -1), 0.75, rule),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    return card


def _authorised_collection_banks_section(
    page_w: float,
    *,
    section_label_style: ParagraphStyle,
    rule: Any,
    bank_bg: Any,
) -> Table:
    col_w = (page_w - 52) / len(AUTHORISED_COLLECTION_BANK_LOGOS)
    logo_max_w = max(col_w - 14, 1.8 * cm)
    logo_max_h = 12 * mm
    cards = [
        _bank_logo_card(
            path,
            rule=rule,
            bank_bg=bank_bg,
            max_logo_w=logo_max_w,
            max_logo_h=logo_max_h,
        )
        for path in AUTHORISED_COLLECTION_BANK_LOGOS
    ]
    banks_grid = Table([cards], colWidths=[col_w] * len(cards))
    banks_grid.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    section = Table(
        [
            [Paragraph("AUTHORISED COLLECTION BANKS", section_label_style)],
            [banks_grid],
        ],
        colWidths=[page_w],
    )
    section.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.75, rule),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ("LEFTPADDING", (0, 0), (-1, -1), 26),
                ("RIGHTPADDING", (0, 0), (-1, -1), 26),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ]
        )
    )
    return section


def _bank_logo_cell(path: Path, max_width: float, max_height: float) -> Image | Paragraph:
    if path.is_file():
        return _scaled_image(path, max_width, max_height)
    fallback = ParagraphStyle(
        "bankFallback",
        fontSize=7,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#6B7C72"),
        fontName="Helvetica",
    )
    return Paragraph(path.stem, fallback)


def _bank_logo_table() -> Table:
    cell_w = 3.3 * cm
    cards = [
        _bank_logo_card(
            path,
            rule=COLOR_BANK_BORDER,
            bank_bg=COLOR_BANK_BG,
            max_logo_w=2.9 * cm,
            max_logo_h=1.1 * cm,
        )
        for path in AUTHORISED_COLLECTION_BANK_LOGOS
    ]
    row = Table([cards], colWidths=[cell_w] * len(cards))
    row.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return row


def _section_header(title: str, styles: dict, *, color: Any = COLOR_ZCAMS_GREEN, width: float = 16.5 * cm) -> Table:
    header = Table([[Paragraph(str(title).upper(), styles["section_header"])]], colWidths=[width])
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), color),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return header


def _cpay_ref_banner(capitalpay_no: str, styles: dict) -> Table:
    """Highlighted CapitalPay reference under the header."""
    inner = Table(
        [[Paragraph(capitalpay_no, styles["cpay_ref"])]],
        colWidths=[14 * cm],
    )
    inner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_CPAY_BG),
                ("BOX", (0, 0), (-1, -1), 1.2, COLOR_CPAY_BLUE),
                ("LINEBEFORE", (0, 0), (0, -1), 5, COLOR_ZCAMS_GREEN),
                ("TOPPADDING", (0, 0), (-1, -1), 11),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    wrapper = Table([[inner]], colWidths=[16.5 * cm])
    wrapper.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    return wrapper


def _detail_grid(
    rows: list[tuple[str, str]],
    styles: dict,
    *,
    highlight_label: str | None = None,
) -> Table:
    data = []
    highlight_idx: int | None = None
    for i, (label, value) in enumerate(rows):
        if highlight_label and label == highlight_label:
            highlight_idx = i
            data.append(
                [
                    Paragraph(label, styles["cpay_label_row"]),
                    Paragraph(str(value or "—"), styles["cpay_value"]),
                ]
            )
        else:
            data.append(
                [
                    Paragraph(label, styles["label"]),
                    Paragraph(str(value or "—"), styles["value"]),
                ]
            )
    table = Table(data, colWidths=[4.2 * cm, 12.3 * cm])
    style_commands: list[Any] = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, COLOR_GRID_LINE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]
    if highlight_idx is not None:
        style_commands.extend(
            [
                ("BACKGROUND", (0, highlight_idx), (-1, highlight_idx), COLOR_CPAY_BG),
                ("BOX", (0, highlight_idx), (-1, highlight_idx), 0.75, COLOR_CPAY_BLUE),
                ("LINEBEFORE", (0, highlight_idx), (0, highlight_idx), 4, COLOR_CPAY_BLUE),
            ]
        )
    table.setStyle(TableStyle(style_commands))
    return table


def _boxed_section(flowables: list[Any], *, border: Any, background: Any) -> Table:
    """Wrap a block (heading + grid) in a coloured panel."""
    panel = Table([[flowables]], colWidths=[16.5 * cm])
    panel.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, border),
                ("LINEBEFORE", (0, 0), (0, -1), 4, border),
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return panel


def _spaced_caps(value: str) -> str:
    return " ".join(str(value or "").upper())


def _money(value: float | int | str | None) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    return f"USD {amount:,.2f}"


def _payment_reference(invoice: dict) -> str:
    return invoice.get("capitalpay_ref") or invoice.get("capitalpay_urn") or invoice.get("invoice_number") or invoice.get("id") or "—"


def _collection_banks_table(styles: dict) -> Table:
    cards = [
        _bank_logo_card(
            path,
            rule=COLOR_BANK_BORDER,
            bank_bg=COLOR_BANK_BG,
            max_logo_w=2.8 * cm,
            max_logo_h=1.1 * cm,
        )
        for path in AUTHORISED_COLLECTION_BANK_LOGOS
    ]
    table = Table([cards], colWidths=[3.25 * cm] * len(cards))
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _notice_detail_rows(rows: list[tuple[str, Any]], styles: dict, *, label_width: float = 5.2 * cm) -> Table:
    data = [
        [
            Paragraph(_spaced_caps(label), styles["tiny_caps"]),
            Paragraph(str(value or "—"), styles["notice_value"]),
        ]
        for label, value in rows
    ]
    table = Table(data, colWidths=[label_width, 16.5 * cm - label_width])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, COLOR_GRID_LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def generate_invoice_pdf(invoice: dict, company: dict) -> Path:
    invoice_id = invoice["id"]
    path = invoice_pdf_path(invoice_id, invoice["invoice_number"])
    styles = _styles()

    settlement = (invoice.get("invoice_type") or "").replace("_", " ").title()
    capitalpay_no = _payment_reference(invoice)
    amount_due = _gn83_total(invoice)
    payment_link = _zcams_checkout_link(invoice)
    issued = invoice.get("signed_at") or invoice.get("created_at") or datetime.now(timezone.utc).isoformat()
    try:
        issued_display = datetime.fromisoformat(issued.replace("Z", "+00:00")).strftime("%d %b %Y %H:%M UTC")
        due_display = datetime.fromisoformat(issued.replace("Z", "+00:00")).strftime("%d %b %Y")
    except ValueError:
        issued_display = str(issued)[:19]
        due_display = invoice.get("due_date") or "On presentation"

    def safe(value: Any, fallback: str = "—") -> str:
        text = str(value if value not in (None, "") else fallback)
        return escape(text)

    def field(label: str, value: Any, *, mono: bool = False) -> list[Any]:
        value_style = ParagraphStyle(
            f"TemplateValue{'Mono' if mono else ''}",
            parent=styles["value"],
            fontName="Courier-Bold" if mono else "Helvetica-Bold",
            fontSize=8.8 if mono else 9.6,
            leading=11.5,
            textColor=colors.HexColor("#111110"),
            spaceAfter=0,
        )
        return [
            Paragraph(safe(label).upper(), template_styles["field_label"]),
            Paragraph(safe(value), value_style),
        ]

    template_styles = {
        "header_org": ParagraphStyle(
            "TemplateHeaderOrg",
            parent=styles["footer"],
            fontSize=6.6,
            leading=8,
            textColor=colors.HexColor("#AAA89F"),
            fontName="Helvetica-Bold",
            alignment=TA_LEFT,
        ),
        "header_brand": ParagraphStyle(
            "TemplateHeaderBrand",
            parent=styles["title"],
            fontSize=15,
            leading=18,
            textColor=colors.white,
            fontName="Helvetica-Bold",
            alignment=TA_LEFT,
        ),
        "header_title": ParagraphStyle(
            "TemplateHeaderTitle",
            parent=styles["title"],
            fontSize=19,
            leading=22,
            textColor=colors.white,
            fontName="Helvetica-Bold",
            alignment=TA_LEFT,
        ),
        "header_muted": ParagraphStyle(
            "TemplateHeaderMuted",
            parent=styles["footer"],
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#AAA89F"),
            alignment=TA_RIGHT,
        ),
        "doc_num": ParagraphStyle(
            "TemplateDocNum",
            parent=styles["value"],
            fontSize=15.5,
            leading=19,
            textColor=colors.white,
            fontName="Courier-Bold",
            alignment=TA_RIGHT,
        ),
        "pill_label": ParagraphStyle(
            "TemplatePillLabel",
            parent=styles["label"],
            fontSize=6.6,
            leading=8,
            textColor=colors.HexColor("#7A7870"),
            fontName="Helvetica-Bold",
        ),
        "pill_value": ParagraphStyle(
            "TemplatePillValue",
            parent=styles["value"],
            fontSize=9.2,
            leading=11,
            textColor=colors.HexColor("#111110"),
            fontName="Courier-Bold",
        ),
        "section_title": ParagraphStyle(
            "TemplateSectionTitle",
            parent=styles["label"],
            fontSize=8.5,
            leading=10,
            textColor=colors.HexColor("#111110"),
            fontName="Helvetica-Bold",
        ),
        "field_label": ParagraphStyle(
            "TemplateFieldLabel",
            parent=styles["label"],
            fontSize=6.4,
            leading=8,
            textColor=colors.HexColor("#7A7870"),
            fontName="Helvetica-Bold",
        ),
        "amount_label": ParagraphStyle(
            "TemplateAmountLabel",
            parent=styles["label"],
            fontSize=7.4,
            leading=9,
            textColor=colors.HexColor("#AAA89F"),
            fontName="Helvetica-Bold",
        ),
        "amount_value": ParagraphStyle(
            "TemplateAmountValue",
            parent=styles["title"],
            fontSize=27,
            leading=31,
            textColor=colors.white,
            fontName="Helvetica-Bold",
        ),
        "body": ParagraphStyle(
            "TemplateBody",
            parent=styles["instruction"],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#3A3935"),
        ),
        "instruction_title": ParagraphStyle(
            "TemplateInstructionTitle",
            parent=styles["label"],
            fontSize=8.5,
            leading=10,
            textColor=COLOR_ZCAMS_GREEN,
            fontName="Helvetica-Bold",
            alignment=TA_LEFT,
        ),
        "instruction_body": ParagraphStyle(
            "TemplateInstructionBody",
            parent=styles["instruction"],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#3A3935"),
            alignment=TA_LEFT,
        ),
        "body_small": ParagraphStyle(
            "TemplateBodySmall",
            parent=styles["instruction"],
            fontSize=8.4,
            leading=12,
            textColor=colors.HexColor("#3A3935"),
        ),
        "bank_name": ParagraphStyle(
            "TemplateBankName",
            parent=styles["bank_name"],
            fontSize=8.4,
            leading=10,
            textColor=colors.HexColor("#111110"),
        ),
        "bank_detail": ParagraphStyle(
            "TemplateBankDetail",
            parent=styles["bank_detail"],
            fontSize=6.7,
            leading=8,
            textColor=colors.HexColor("#7A7870"),
            alignment=0,
        ),
        "footer_title": ParagraphStyle(
            "TemplateFooterTitle",
            parent=styles["value"],
            fontSize=9.4,
            leading=12,
            textColor=colors.HexColor("#111110"),
            fontName="Helvetica-Bold",
            spaceAfter=2,
        ),
        "footer_body": ParagraphStyle(
            "TemplateFooterBody",
            parent=styles["footer"],
            fontSize=7.7,
            leading=11,
            textColor=colors.HexColor("#3A3935"),
            alignment=0,
        ),
        "footer_meta": ParagraphStyle(
            "TemplateFooterMeta",
            parent=styles["footer"],
            fontSize=6.9,
            leading=9,
            textColor=colors.HexColor("#7A7870"),
            alignment=0,
            fontName="Courier",
        ),
        "stamp": ParagraphStyle(
            "TemplateStamp",
            parent=styles["footer"],
            fontSize=6.2,
            leading=8,
            textColor=colors.HexColor("#A0A09A"),
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        ),
    }

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=0.85 * cm,
        rightMargin=0.85 * cm,
        topMargin=0.75 * cm,
        bottomMargin=0.75 * cm,
        title=f"ZCAMS Invoice {invoice.get('invoice_number')}",
        author=company.get("name", "ZCAMS"),
    )

    page_w = A4[0] - doc.leftMargin - doc.rightMargin
    accent = colors.HexColor("#1A1A18")
    rule = colors.HexColor("#D6D3CC")
    bank_bg = colors.HexColor("#F0EDE8")
    gold_bg = colors.HexColor("#FDF6E3")
    footer_bg = colors.HexColor("#FAFAF8")

    if INVOICE_LOGO_PATH.is_file():
        logo_mark = _scaled_image(INVOICE_LOGO_PATH, 14 * mm, 14 * mm)
    else:
        logo_mark = Table(
            [[Paragraph("ZC", ParagraphStyle("LogoTop", fontSize=11, leading=12, fontName="Helvetica-Bold", alignment=TA_CENTER, textColor=accent))],
             [Paragraph("AMS", ParagraphStyle("LogoBot", fontSize=5, leading=6, fontName="Helvetica-Bold", alignment=TA_CENTER, textColor=accent))]],
            colWidths=[12 * mm],
            rowHeights=[6.5 * mm, 4.5 * mm],
        )
        logo_mark.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#D9B650")),
                    ("BOX", (0, 0), (-1, -1), 0, colors.HexColor("#D9B650")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
    logo_text = [
        Paragraph("ZAMBIA CLEARING AGENCY MANAGEMENT SYSTEM", template_styles["header_org"]),
        Paragraph("ZCAMS", template_styles["header_brand"]),
    ]
    header_left = [
        Table([[logo_mark, logo_text]], colWidths=[14 * mm, 82 * mm], style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ]),
        Spacer(1, 5 * mm),
        Paragraph("Auto-Generated Invoice", template_styles["header_title"]),
    ]
    header_right = [
        Paragraph("BANK INVOICE REF", template_styles["header_muted"]),
        Paragraph(safe(capitalpay_no), template_styles["doc_num"]),
        Spacer(1, 2 * mm),
        Paragraph(f"Settlement due: <b>{safe(due_display)}</b>", template_styles["header_muted"]),
    ]
    header = Table([[header_left, header_right]], colWidths=[page_w * 0.62, page_w * 0.38])
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), accent),
                ("LEFTPADDING", (0, 0), (0, 0), 26),
                ("RIGHTPADDING", (0, 0), (0, 0), 12),
                ("LEFTPADDING", (1, 0), (1, 0), 12),
                ("RIGHTPADDING", (1, 0), (1, 0), 26),
                ("TOPPADDING", (0, 0), (-1, -1), 22),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 22),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ]
        )
    )

    def pill(code: str, label: str, value: Any, bg: str, fg: str) -> list[Any]:
        icon_style = ParagraphStyle("PillIcon", fontSize=7.2, leading=9, fontName="Helvetica-Bold", alignment=TA_CENTER, textColor=colors.HexColor(fg))
        icon = Table([[Paragraph(code, icon_style)]], colWidths=[9.5 * mm], rowHeights=[9.5 * mm])
        icon.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(fg)),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        text = [Paragraph(safe(label).upper(), template_styles["pill_label"]), Paragraph(safe(value), template_styles["pill_value"])]
        return [icon, text]

    pill_row = Table(
        [
            [
                Table([pill("ZSD", "Z-SAD Number", invoice.get("z_sad_number"), "#FFF3CD", "#8A6200")], colWidths=[12 * mm, 49 * mm]),
                Table([pill("INV", "Invoice Number", invoice.get("invoice_number"), "#E8F0FE", "#1A47A8")], colWidths=[12 * mm, 55 * mm]),
                Table([pill("CPY", "CapitalPay No (Bank Invoice Ref)", capitalpay_no, "#E6F4EA", "#1A6E35")], colWidths=[12 * mm, 52 * mm]),
            ]
        ],
        colWidths=[page_w * 0.32, page_w * 0.34, page_w * 0.34],
    )
    pill_row.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.75, rule),
                ("LINEBELOW", (0, 0), (-1, -1), 0.75, rule),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                ("LEFTPADDING", (0, 0), (-1, -1), 26),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )

    company_name = company.get("name") or invoice.get("company_name") or "ZCAMS Customer"
    company_tpin = company.get("tpin") or invoice.get("consignee_tin") or "—"
    company_email = company.get("company_email") or invoice.get("contact_email") or "—"
    cargo_category = (invoice.get("gn83_category") or settlement or "—").replace("_", " ").title()
    shipment_reference = invoice.get("bl_number") or invoice.get("reviewed_bl_id") or "—"
    if invoice.get("cargo_description"):
        cargo_category = f"{cargo_category}, {invoice.get('cargo_description')}"

    left_body = [
        Paragraph("INVOICE TO", template_styles["section_title"]),
        Spacer(1, 4 * mm),
        *field("Company", company_name),
        Spacer(1, 2 * mm),
        *field("TIN / Tax ID", company_tpin, mono=True),
        Spacer(1, 2 * mm),
        *field("Email", company_email),
    ]
    right_body = [
        Paragraph("Z-SAD REFERENCE", template_styles["section_title"]),
        Spacer(1, 4 * mm),
        *field("Z-SAD Number", invoice.get("z_sad_number"), mono=True),
        Spacer(1, 2 * mm),
        *field("Shipment Reference", shipment_reference, mono=True),
        Spacer(1, 2 * mm),
        *field("Cargo Category", cargo_category),
    ]
    body_grid = Table([[left_body, right_body]], colWidths=[page_w / 2, page_w / 2])
    body_grid.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.75, rule),
                ("LINEBEFORE", (1, 0), (1, 0), 0.75, rule),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 19),
                ("TOPPADDING", (0, 0), (-1, -1), 19),
                ("LEFTPADDING", (0, 0), (-1, -1), 26),
                ("RIGHTPADDING", (0, 0), (-1, -1), 26),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    amount_left = [
        Paragraph("TOTAL AMOUNT DUE", template_styles["amount_label"]),
        Spacer(1, 3 * mm),
        Paragraph(f"USD {amount_due:,.2f}", template_styles["amount_value"]),
    ]
    amount_right = [
        Paragraph(
            "This notice authorises collection of the stated amount at any authorised ZCAMS partner bank. "
            "Present this document together with your company identification.",
            template_styles["body"],
        ),
        Spacer(1, 3 * mm),
        Paragraph(
            f'Bank Invoice Ref: <font backColor="#FDF6E3"><b>{safe(capitalpay_no)}</b></font> — must be quoted on all bank transactions.',
            template_styles["body"],
        ),
    ]
    amount_band = Table([[amount_left, amount_right]], colWidths=[page_w * 0.34, page_w * 0.66])
    amount_band.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), accent),
                ("BACKGROUND", (1, 0), (1, 0), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.75, rule),
                ("TOPPADDING", (0, 0), (-1, -1), 22),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 22),
                ("LEFTPADDING", (0, 0), (0, 0), 26),
                ("RIGHTPADDING", (0, 0), (0, 0), 20),
                ("LEFTPADDING", (1, 0), (1, 0), 22),
                ("RIGHTPADDING", (1, 0), (1, 0), 26),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )

    banks_section = _authorised_collection_banks_section(
        page_w,
        section_label_style=template_styles["pill_label"],
        rule=rule,
        bank_bg=bank_bg,
    )

    instruction_text = (
        "Present this invoice at an accepted bank and quote the Bank Invoice reference exactly as shown. "
        "Ensure the narration matches the reference above."
    )
    if payment_link:
        instruction_text += (
            '<br/><br/><font color="#06451F"><b>Secure ZCAMS checkout link:</b></font> '
            f'<font backColor="#EAF6EC" color="#06451F"><b>{safe(payment_link)}</b></font>'
        )
    instruction_section = Table(
        [
            [Paragraph("PAYMENT INSTRUCTION", template_styles["instruction_title"])],
            [Paragraph(instruction_text, template_styles["instruction_body"])],
        ],
        colWidths=[page_w],
    )
    instruction_section.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_MINT_BG),
                ("BOX", (0, 0), (-1, -1), 0.75, rule),
                ("LINEBEFORE", (0, 0), (0, -1), 4, COLOR_ZCAMS_GREEN),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                ("LEFTPADDING", (0, 0), (-1, -1), 26),
                ("RIGHTPADDING", (0, 0), (-1, -1), 26),
            ]
        )
    )

    footer_text = [
        Paragraph("Official Payment Collection Notice — ZCAMS", template_styles["footer_title"]),
        Paragraph(
            "This document is computer-generated by the Zambia Clearing Agency Management System (ZCAMS) and is valid without a physical "
            "signature. It constitutes an official payment notice under the ZCAMS regulatory framework. Retain this document and the bank "
            "receipt as proof of payment.",
            template_styles["footer_body"],
        ),
        Spacer(1, 2 * mm),
        Paragraph(f"Generated: {safe(issued_display)} &nbsp;·&nbsp; Bank Invoice Ref: {safe(capitalpay_no)} &nbsp;·&nbsp; zcams.info", template_styles["footer_meta"]),
    ]
    stamp = Table([[Paragraph("ZCAMS<br/>CERTIFIED<br/>DOCUMENT", template_styles["stamp"])]], colWidths=[18 * mm], rowHeights=[18 * mm])
    stamp.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#C0BDB5")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    footer = Table([[footer_text, stamp]], colWidths=[page_w - 28 * mm, 28 * mm])
    footer.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), footer_bg),
                ("BOX", (0, 0), (-1, -1), 0.75, rule),
                ("TOPPADDING", (0, 0), (-1, -1), 16),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
                ("LEFTPADDING", (0, 0), (-1, -1), 26),
                ("RIGHTPADDING", (0, 0), (-1, -1), 26),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    story: list[Any] = [
        header,
        pill_row,
        body_grid,
        amount_band,
        banks_section,
        instruction_section,
        footer,
    ]

    doc.build(story)
    return path


def invoice_print_html(invoice: dict) -> str:
    return f"<p>Download PDF for invoice {invoice.get('invoice_number')}</p>"


def contract_print_html(contract: dict) -> str:
    return (
        f"<h1>ZCAMS Contract {contract.get('contract_no')}</h1>"
        f"<p>Importer: {contract.get('importer_name')}</p>"
        f"<p>Status: {contract.get('status')}</p>"
    )
