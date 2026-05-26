from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
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


INVOICE_PDF_DIR = DATA_DIR / "invoices"
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
INVOICE_LOGO_PATH = ASSETS_DIR / "zcams-logo.png"
CAPITALPAY_LOGO_PATH = ASSETS_DIR / "capitalPay.png"

# Five major retail banks in Zambia — logo PNGs in assets/ (display order).
ZAMBIA_BANK_LOGOS: list[Path] = [
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
    max_logo_w = 2.9 * cm
    max_logo_h = 1.1 * cm
    cells = [_bank_logo_cell(path, max_logo_w, max_logo_h) for path in ZAMBIA_BANK_LOGOS]
    row = Table([cells], colWidths=[cell_w] * len(cells))
    row.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1.25, COLOR_BANK_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_GRID_LINE),
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_BANK_BG),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
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
    banks = [
        ("Z", "Zanaco", "Cairo Road Branch", "SWIFT: ZNCOZMLU"),
        ("ABSA", "ABSA", "Cairo Road Branch", "SWIFT: BARCZMLU"),
        ("S", "Stanbic", "Lusaka Main Branch", "SWIFT: SBICZMLX"),
        ("E", "Ecobank", "Cairo Road Branch", "SWIFT: ECOCZMLU"),
        ("SC", "Stanchart", "Cairo Road Branch", "SWIFT: SCBLZMLU"),
    ]
    cells = []
    for code, name, branch, swift in banks:
        cells.append(
            [
                Paragraph(code, styles["bank_name"]),
                Paragraph(name, styles["bank_name"]),
                Paragraph(branch, styles["bank_detail"]),
                Paragraph(swift, styles["bank_detail"]),
            ]
        )
    table = Table([cells], colWidths=[3.25 * cm] * len(cells))
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, COLOR_ZCAMS_GREEN),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, COLOR_GRID_LINE),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FBF6")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
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
    checkout = _capitalpay_checkout(invoice)
    issued = invoice.get("signed_at") or invoice.get("created_at") or datetime.now(timezone.utc).isoformat()
    try:
        issued_display = datetime.fromisoformat(issued.replace("Z", "+00:00")).strftime("%d %b %Y %H:%M UTC")
    except ValueError:
        issued_display = str(issued)[:19]

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title=f"ZCAMS Invoice {invoice.get('invoice_number')}",
        author=company.get("name", "ZCAMS"),
    )

    story: list[Any] = []

    logo = _invoice_logo_image()
    if logo:
        story.append(_centered_block([logo]))
        story.append(Spacer(1, 5 * mm))

    story.append(
        _centered_block(
            [
                Paragraph("CapitalPay Signed Invoice", styles["cpay_label"]),
                Spacer(1, 4 * mm),
            ]
        )
    )
    story.append(_cpay_ref_banner(capitalpay_no, styles))
    story.append(Spacer(1, 4 * mm))
    story.append(
        _centered_block(
            [
                Paragraph(f"{company.get('name', 'Clearing & Forwarding Agent')}", styles["center_sub"]),
                Paragraph("GN 83 Compliant Customs Agency Invoice", styles["center_sub"]),
            ]
        )
    )
    story.append(Spacer(1, 8 * mm))

    story.append(_section_header("Partner banking network — Zambia", styles))
    story.append(Spacer(1, 1.5 * mm))
    story.append(_bank_logo_table())
    story.append(Spacer(1, 8 * mm))

    story.append(
        _boxed_section(
            [
                _section_header("Invoice details", styles, color=COLOR_ZCAMS_GREEN_DARK, width=15.8 * cm),
                Spacer(1, 2 * mm),
                _detail_grid(
                    [
                        ("ZCAMS invoice no.", invoice.get("invoice_number")),
                        ("CapitalPay invoice no.", capitalpay_no),
                        ("Settlement type", settlement),
                        ("Invoice status", invoice.get("status", "AWAITING_PAYMENT")),
                        ("Date issued", issued_display),
                        ("Due date", invoice.get("due_date") or "—"),
                    ],
                    styles,
                    highlight_label="CapitalPay invoice no.",
                ),
            ],
            border=COLOR_ZCAMS_GREEN,
            background=COLOR_PANEL_BG,
        )
    )
    story.append(Spacer(1, 6 * mm))

    story.append(
        _boxed_section(
            [
                _section_header("Shipment & Z-SAD reference", styles, color=COLOR_ZCAMS_GREEN, width=15.8 * cm),
                Spacer(1, 2 * mm),
                _detail_grid(
                    [
                        ("Bill of Lading", invoice.get("bl_number")),
                        ("Z-SAD number", invoice.get("z_sad_number")),
                        ("Consignee", invoice.get("consignee_name")),
                        ("Consignee TPIN", invoice.get("consignee_tin")),
                    ],
                    styles,
                    highlight_label="Z-SAD number",
                ),
            ],
            border=COLOR_ZCAMS_GREEN,
            background=COLOR_PANEL_BG,
        )
    )
    story.append(Spacer(1, 6 * mm))

    story.append(
        _boxed_section(
            [
                _section_header("Importer contact", styles, color=COLOR_IMPORTER_GREEN, width=15.8 * cm),
                Spacer(1, 2 * mm),
                Paragraph("Importer contact", styles["section_importer"]),
                _detail_grid(
                    [
                        ("Contact phone", invoice.get("contact_phone")),
                        ("Contact email", invoice.get("contact_email")),
                    ],
                    styles,
                ),
            ],
            border=COLOR_IMPORTER_GREEN,
            background=COLOR_IMPORTER_BG,
        )
    )

    if invoice.get("invoice_type") == "FULL_SETTLEMENT":
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph("Beneficiary settlement details", styles["label"]))
        story.append(Spacer(1, 2 * mm))
        story.append(
            _detail_grid(
                [
                    ("Beneficiary name", invoice.get("beneficiary_name")),
                    ("Bank name", invoice.get("beneficiary_bank_name")),
                    ("Account number", invoice.get("beneficiary_account_number")),
                ],
                styles,
            )
        )

    story.append(Spacer(1, 10 * mm))
    amount_rows: list[list[Any]] = [
        [Paragraph("Amount due (USD)", styles["label_on_green"]), Paragraph(f"USD {amount_due:,.2f}", styles["total_on_green"])],
    ]
    if checkout is not None:
        amount_rows.append(
            [
                Paragraph("CapitalPay checkout (USD)", styles["label_on_green"]),
                Paragraph(f"USD {checkout:,.2f}", styles["total_on_green"]),
            ]
        )
    total_box = Table(amount_rows, colWidths=[10 * cm, 6.3 * cm])
    total_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_ZCAMS_GREEN),
                ("BOX", (0, 0), (-1, -1), 1.2, COLOR_ZCAMS_GREEN_DARK),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("LINEBEFORE", (0, 0), (0, -1), 5, COLOR_ZCAMS_GREEN_DARK),
            ]
        )
    )
    story.append(total_box)
    story.append(Spacer(1, 6 * mm))

    if invoice.get("secure_link") or invoice.get("checkout_url"):
        story.append(
            _boxed_section(
                [
                    Paragraph(
                        f"<b>Payment reference:</b> {capitalpay_no}<br/>"
                        f"<b>Secure payment link:</b> {invoice.get('secure_link') or invoice.get('checkout_url')}",
                        styles["subtitle"],
                    )
                ],
                border=COLOR_CPAY_BLUE,
                background=COLOR_CPAY_BG,
            )
        )

    story.append(Spacer(1, 12 * mm))
    story.append(
        Paragraph(
            f"{company.get('name', 'ZCAMS')} · {company.get('address_line1', '')} {company.get('city', '')} · "
            f"Tel {company.get('phone', '—')} · {company.get('company_email', '—')}<br/>"
            "This invoice is digitally signed through CapitalPay. Present the CapitalPay invoice number when paying.",
            styles["footer"],
        )
    )

    draw_footer_logo = _footer_company_logo(company)
    doc.build(story, onFirstPage=draw_footer_logo, onLaterPages=draw_footer_logo)
    return path


def invoice_print_html(invoice: dict) -> str:
    return f"<p>Download PDF for invoice {invoice.get('invoice_number')}</p>"


def contract_print_html(contract: dict) -> str:
    return (
        f"<h1>ZCAMS Contract {contract.get('contract_no')}</h1>"
        f"<p>Importer: {contract.get('importer_name')}</p>"
        f"<p>Status: {contract.get('status')}</p>"
    )
