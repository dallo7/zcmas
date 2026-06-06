"""Capture live ZCAMS screenshots and build a Z-SAD / invoice tutorial PDF."""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from services import repository


APP_URL = "http://127.0.0.1:8050"
DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
SCREENSHOT_DIR = DOCS_DIR / "tutorial-screenshots"
PDF_PATH = DOCS_DIR / "ZCAMS_ZSAD_Invoice_Live_Screenshot_Tutorial.pdf"

GREEN = colors.HexColor("#06451F")
GREEN_DARK = colors.HexColor("#031F0C")
GREEN_SOFT = colors.HexColor("#EAF6EC")
PANEL = colors.HexColor("#FBFEFB")
YELLOW = colors.HexColor("#F5B700")
ORANGE = colors.HexColor("#EF7D00")
TEXT = colors.HexColor("#1A2E24")
MUTED = colors.HexColor("#4A5D52")
GRID = colors.HexColor("#CFE3D4")
WHITE = colors.white


class DevToolsClient:
    """Tiny Chrome DevTools Protocol client using only the standard library."""

    def __init__(self, websocket_url: str):
        parsed = urlparse(websocket_url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 80
        self.path = parsed.path
        if parsed.query:
            self.path += f"?{parsed.query}"
        self.sock = socket.create_connection((self.host, self.port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = self.sock.recv(4096)
        if b" 101 " not in response:
            raise RuntimeError(f"Chrome DevTools websocket upgrade failed: {response[:200]!r}")
        self.next_id = 1

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def _send_frame(self, payload: bytes) -> None:
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(header + masked)

    def _recv_exact(self, size: int) -> bytes:
        chunks = []
        remaining = size
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise RuntimeError("Chrome DevTools websocket closed unexpectedly.")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _recv_frame(self) -> dict:
        while True:
            first, second = self._recv_exact(2)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if masked else b""
            payload = self._recv_exact(length) if length else b""
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 8:
                raise RuntimeError("Chrome DevTools websocket closed.")
            if opcode == 1:
                return json.loads(payload.decode("utf-8"))

    def send(self, method: str, params: dict | None = None) -> dict:
        message_id = self.next_id
        self.next_id += 1
        self._send_frame(json.dumps({"id": message_id, "method": method, "params": params or {}}).encode("utf-8"))
        while True:
            message = self._recv_frame()
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(f"CDP error for {method}: {message['error']}")
                return message

    def evaluate(self, expression: str, await_promise: bool = False):
        result = self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
            },
        )["result"]["result"]
        return result.get("value")

    def navigate(self, url: str) -> None:
        self.send("Page.navigate", {"url": url})
        self.wait_for("document.readyState === 'complete'", timeout=20)
        time.sleep(1.3)

    def wait_for(self, expression: str, timeout: int = 15) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.evaluate(expression):
                    return
            except Exception:
                pass
            time.sleep(0.35)
        raise TimeoutError(f"Timed out waiting for: {expression}")

    def screenshot(self, path: Path) -> None:
        metrics = self.send("Page.getLayoutMetrics")["result"]["cssVisualViewport"]
        shot = self.send(
            "Page.captureScreenshot",
            {
                "format": "png",
                "fromSurface": True,
                "clip": {
                    "x": 0,
                    "y": 0,
                    "width": min(float(metrics.get("clientWidth") or 1365), 1365.0),
                    "height": min(float(metrics.get("clientHeight") or 900), 900.0),
                    "scale": 1,
                },
            },
        )["result"]["data"]
        path.write_bytes(base64.b64decode(shot))


def _chrome_path() -> str:
    candidates = [
        os.environ.get("CHROME_PATH", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise FileNotFoundError("Chrome or Edge was not found. Set CHROME_PATH to the browser executable.")


def _open_devtools_tab(port: int, url: str) -> str:
    encoded = quote(url, safe=":/?=&")
    request = Request(f"http://127.0.0.1:{port}/json/new?{encoded}", method="PUT")
    try:
        with urlopen(request, timeout=10) as response:
            tab = json.loads(response.read().decode("utf-8"))
    except Exception:
        with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=10) as response:
            tabs = json.loads(response.read().decode("utf-8"))
            tab = tabs[0]
    return tab["webSocketDebuggerUrl"]


def _seed_tutorial_bl() -> dict:
    repository.bootstrap()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    bl_number = f"TUT-ZSAD-{stamp}"
    return repository.create_bl(
        {
            "bl_number": bl_number,
            "doc_type": "Bill of Lading",
            "route_type": "Import",
            "transport_mode": "Sea",
            "zra_regime": "IMPORT_HOME_USE",
            "shipper_name": "Tutorial Exporter Ltd",
            "shipper_address": "Port of Durban",
            "shipper_country": "South Africa",
            "carrier_name": "ZCAMS Tutorial Line",
            "vessel_vehicle_no": "TUT-VESSEL-01",
            "origin": "Durban",
            "destination": "Lusaka",
            "consignee_tin": "1000123456",
            "consignee_name": "Tutorial Importer Zambia",
            "gross_weight": 12000,
            "no_containers": 2,
            "file_name": "tutorial-zsad-bl.pdf",
            "cargo_description": "Tutorial motor vehicle consignment",
            "hs_code": "8703",
            "gn83_category": "MOTOR_VEHICLE",
        },
        auto_review=False,
        use_ocr_defaults=False,
    )


def _set_input_js(selector: str, value: str) -> str:
    return f"""
    (() => {{
      const el = document.querySelector({json.dumps(selector)});
      if (!el) return false;
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(el, {json.dumps(value)});
      el.dispatchEvent(new Event('input', {{ bubbles: true }}));
      el.dispatchEvent(new Event('change', {{ bubbles: true }}));
      return true;
    }})()
    """


def _click_text_js(text: str) -> str:
    return f"""
    (() => {{
      const btn = [...document.querySelectorAll('button')].find((b) => b.textContent.trim().includes({json.dumps(text)}));
      if (!btn) return false;
      btn.scrollIntoView({{ block: 'center', inline: 'center' }});
      btn.click();
      return true;
    }})()
    """


def capture_live_screenshots() -> list[tuple[str, str, Path]]:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    _seed_tutorial_bl()
    port = 9224
    user_data = tempfile.TemporaryDirectory(prefix="zcams-chrome-")
    chrome = subprocess.Popen(
        [
            _chrome_path(),
            "--headless=new",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data.name}",
            "--window-size=1365,900",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client: DevToolsClient | None = None
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                websocket = _open_devtools_tab(port, f"{APP_URL}/login")
                break
            except Exception:
                time.sleep(0.4)
        else:
            raise TimeoutError("Chrome DevTools did not become available.")

        client = DevToolsClient(websocket)
        client.send("Page.enable")
        client.send("Runtime.enable")
        client.send("Emulation.setDeviceMetricsOverride", {"width": 1365, "height": 900, "deviceScaleFactor": 1, "mobile": False})

        shots: list[tuple[str, str, Path]] = []

        def save(name: str, title: str, caption: str) -> None:
            path = SCREENSHOT_DIR / name
            client.screenshot(path)
            shots.append((title, caption, path))

        client.navigate(f"{APP_URL}/login")
        client.wait_for("!!document.querySelector('#login-email')")
        save("01-login.png", "1. Sign in to ZCAMS", "Open the ZCAMS login page and sign in with an operational user.")

        client.evaluate(_set_input_js("#login-email", "companyadmin"))
        client.evaluate(_set_input_js("#login-password", "demo123"))
        client.evaluate("document.querySelector('#login-submit').click()")
        client.wait_for("window.location.pathname !== '/login'", timeout=20)
        time.sleep(2.5)
        save("02-dashboard.png", "2. Confirm the operational dashboard", "After sign-in, the dashboard shows the workflow and quick actions.")

        client.navigate(f"{APP_URL}/reviewed-bl")
        client.wait_for("document.body.innerText.includes('BLs Awaiting Review')", timeout=20)
        save("03-awaiting-review.png", "3. Open Reviewed BL", "The tutorial BL appears in BLs Awaiting Review with the Review & Issue Z-SAD action.")

        if not client.evaluate(_click_text_js("Review & Issue Z-SAD")):
            raise RuntimeError("Could not find the Review & Issue Z-SAD button.")
        client.wait_for("document.body.innerText.includes('Z-SAD issued') || document.body.innerText.includes('Z-SAD-')", timeout=20)
        time.sleep(1.5)
        save("04-zsad-issued.png", "4. Issue the Z-SAD", "Click Review & Issue Z-SAD. The BL moves into Active Reviewed BLs with a Z-SAD number.")

        if not client.evaluate(_click_text_js("Service")):
            raise RuntimeError("Could not find the Service invoice button.")
        client.wait_for("!!document.querySelector('#invoice-request-modal') && !document.querySelector('#invoice-request-modal').className.includes('is-hidden')", timeout=20)
        time.sleep(1.3)
        save("05-agency-charge-invoice.png", "5. Prepare a Full Settlement invoice", "Choose Full Settlement to calculate the GN 83 total and settlement amount.")

        client.evaluate("document.querySelector('#invoice-modal-close')?.click()")
        time.sleep(1.0)
        if not client.evaluate(_click_text_js("Full Settlement")):
            raise RuntimeError("Could not find the Full Settlement invoice button.")
        client.wait_for("!!document.querySelector('#invoice-request-modal') && !document.querySelector('#invoice-request-modal').className.includes('is-hidden')", timeout=20)
        client.evaluate(_set_input_js("#invoice-full-amount", "250"))
        client.evaluate(_set_input_js("#invoice-beneficiary-name", "Tutorial Importer Zambia"))
        client.evaluate(_set_input_js("#invoice-beneficiary-bank", "ZANACO"))
        client.evaluate(_set_input_js("#invoice-beneficiary-account", "1234567890"))
        client.evaluate("const cb=document.querySelector('#invoice-bank-confirm input'); if (cb && !cb.checked) cb.click();")
        time.sleep(1.5)
        save("06-full-settlement-invoice.png", "6. Prepare a Full Settlement invoice", "Choose Full Settlement, enter beneficiary banking details, then use Pay Now or Generate & Share Invoice.")

        return shots
    finally:
        if client:
            client.close()
        chrome.terminate()
        try:
            chrome.wait(timeout=5)
        except subprocess.TimeoutExpired:
            chrome.kill()
        user_data.cleanup()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("LiveTitle", parent=base["Heading1"], fontSize=23, leading=28, textColor=GREEN_DARK, fontName="Helvetica-Bold"),
        "subtitle": ParagraphStyle("LiveSubtitle", parent=base["Normal"], fontSize=11.5, leading=15, textColor=MUTED),
        "h1": ParagraphStyle("LiveH1", parent=base["Heading1"], fontSize=15, leading=19, textColor=GREEN, fontName="Helvetica-Bold", spaceAfter=6),
        "body": ParagraphStyle("LiveBody", parent=base["Normal"], fontSize=9.4, leading=12.8, textColor=TEXT, spaceAfter=5),
        "small": ParagraphStyle("LiveSmall", parent=base["Normal"], fontSize=8, leading=10, textColor=MUTED),
    }


def _header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(GREEN_DARK)
    canvas.rect(0, A4[1] - 13 * mm, A4[0], 13 * mm, stroke=0, fill=1)
    canvas.setFillColor(YELLOW)
    canvas.rect(0, A4[1] - 13 * mm, 22 * mm, 13 * mm, stroke=0, fill=1)
    canvas.setFillColor(ORANGE)
    canvas.rect(22 * mm, A4[1] - 13 * mm, 8 * mm, 13 * mm, stroke=0, fill=1)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(2 * cm, A4[1] - 8.2 * mm, "ZCAMS Live Screenshot Tutorial")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(2 * cm, 9 * mm, "Z-SAD and invoice generation workflow")
    canvas.drawRightString(A4[0] - 2 * cm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _screenshot_image(path: Path, max_width: float = 16.8 * cm) -> Image:
    with PILImage.open(path) as img:
        width, height = img.size
    ratio = height / width
    return Image(str(path), width=max_width, height=max_width * ratio)


def build_pdf(shots: list[tuple[str, str, Path]]) -> Path:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    story: list = [
        Spacer(1, 8 * mm),
        Paragraph("ZCAMS Z-SAD And Invoice Live Screenshot Tutorial", styles["title"]),
        Paragraph(
            "A practical screenshot guide showing how an operational user signs in, opens Reviewed BL, issues a Z-SAD, and prepares Full Settlement invoices.",
            styles["subtitle"],
        ),
        Spacer(1, 5 * mm),
        Table(
            [
                ["Output", "Live screenshot tutorial"],
                ["Source", APP_URL],
                ["Generated", datetime.now(timezone.utc).strftime("%d %B %Y %H:%M UTC")],
            ],
            colWidths=[3.5 * cm, 13.2 * cm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), GREEN_SOFT),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("BOX", (0, 0), (-1, -1), 0.5, GREEN),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, GRID),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            ),
        ),
        Spacer(1, 6 * mm),
        Paragraph(
            "The screenshots were captured from the local running ZCAMS app using a temporary tutorial BL. The tutorial BL is for documentation only and the database artifact is not intended for deployment.",
            styles["body"],
        ),
        PageBreak(),
    ]
    for title, caption, path in shots:
        story.extend(
            [
                Paragraph(title, styles["h1"]),
                Paragraph(caption, styles["body"]),
                _screenshot_image(path),
                Spacer(1, 4 * mm),
                PageBreak(),
            ]
        )
    doc = SimpleDocTemplate(str(PDF_PATH), pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm, topMargin=2.1 * cm, bottomMargin=1.8 * cm)
    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return PDF_PATH


def build_live_screenshot_tutorial() -> Path:
    shots = capture_live_screenshots()
    return build_pdf(shots)


def main() -> None:
    print(build_live_screenshot_tutorial())


if __name__ == "__main__":
    main()
