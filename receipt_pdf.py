"""Geração do comprovante histórico de retirada em PDF."""
import base64
from datetime import datetime
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from core import TZ


def _value(row, key):
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def _display(value, money=False):
    if value is None or value == "":
        return "Não registrado"
    return f"R$ {float(value):.2f}".replace(".", ",") if money else str(value)


def _local_datetime(value):
    if not value:
        return "Não registrado"
    return datetime.fromisoformat(value).astimezone(TZ).strftime("%d/%m/%Y %H:%M")


def _document(withdrawal):
    document_type = _value(withdrawal, "document_type")
    number = _value(withdrawal, "receiver_document")
    if not document_type and not number:
        return "Não registrado"
    return " ".join(part for part in (_display(document_type), _display(number)) if part != "Não registrado")


class _ReceiptCanvas:
    """Desenha texto com quebra automática e cria páginas somente quando necessário."""

    def __init__(self, output, title, address):
        self.pdf = canvas.Canvas(output, pagesize=A4, pageCompression=0)
        self.width, self.height = A4
        self.margin = 45
        self.address = address
        self.pdf.setTitle(title)
        self._header()

    def _header(self):
        self.pdf.setFont("Helvetica-Bold", 16)
        self.pdf.drawString(self.margin, self.height - 45, "PONTO DE COLETA ADELINHA")
        self.pdf.setFont("Helvetica", 9)
        self.pdf.drawString(self.margin, self.height - 62, "CNPJ: 38.145.273/0001-05")
        self.pdf.drawString(self.margin, self.height - 76, self.address)
        self.pdf.drawString(self.margin, self.height - 90, "WhatsApp: (16) 98800-4966")
        self.y = self.height - 112

    def _new_page(self):
        self.pdf.showPage()
        self._header()

    def ensure(self, height):
        if self.y - height < self.margin:
            self._new_page()

    def line(self, text, bold=False, size=9, leading=13):
        font = "Helvetica-Bold" if bold else "Helvetica"
        available = self.width - 2 * self.margin
        words = []
        for word in str(text).split():
            if stringWidth(word, font, size) <= available:
                words.append(word)
                continue
            chunk = ""
            for character in word:
                if chunk and stringWidth(chunk + character, font, size) > available:
                    words.append(chunk)
                    chunk = character
                else:
                    chunk += character
            if chunk:
                words.append(chunk)
        lines, current = [], ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if not current or stringWidth(candidate, font, size) <= available:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current or " ")
        self.ensure(len(lines) * leading)
        self.pdf.setFont(font, size)
        for wrapped in lines:
            self.pdf.drawString(self.margin, self.y, wrapped)
            self.y -= leading

    def signature(self, value):
        self.ensure(125)
        self.line("Assinatura de quem retirou:", bold=True)
        if value and value.startswith("data:image/png;base64,"):
            image_data = base64.b64decode(value.split(",", 1)[1])
            self.pdf.drawImage(ImageReader(BytesIO(image_data)), self.margin, self.y - 92,
                               width=260, height=88, preserveAspectRatio=True, anchor="sw")
            self.y -= 98
        else:
            self.line("Não registrado")


def build_receipt_pdf(withdrawal, packages, address):
    """Gera o PDF apenas com snapshots persistidos no momento da retirada."""
    output = BytesIO()
    package_id = _display(_value(withdrawal, "package_public_id"))
    document = _ReceiptCanvas(output, f"Comprovante {package_id}", address)
    final_total = _value(withdrawal, "final_total")
    if final_total is None:
        final_total = _value(withdrawal, "total_paid")
    fields = (
        ("Pacote consultado", package_id),
        ("Cliente", _display(_value(withdrawal, "snapshot_client_name"))),
        ("ID do cliente", _display(_value(withdrawal, "snapshot_client_public_id"))),
        ("Retirado por", _display(_value(withdrawal, "receiver_name"))),
        ("Documento", _document(withdrawal)),
        ("Data e hora", _local_datetime(_value(withdrawal, "picked_at"))),
        ("Valor do serviço", _display(_value(withdrawal, "service_amount"), True)),
        ("Dias de atraso", _display(_value(withdrawal, "late_days"))),
        ("Taxa extra", _display(_value(withdrawal, "late_amount"), True)),
        ("Acréscimo manual", _display(_value(withdrawal, "surcharge_amount"), True)),
        ("Motivo do acréscimo", _display(_value(withdrawal, "surcharge_reason"))),
        ("Total final pago", _display(final_total, True)),
        ("Forma de pagamento", _display(_value(withdrawal, "payment_method"))),
    )
    for label, value in fields:
        document.line(f"{label}: {value}")

    document.line("Pacotes desta retirada:", bold=True)
    for item in packages:
        document.line(
            f"{_display(_value(item, 'package_public_id'))} | "
            f"rastreio {_display(_value(item, 'tracking_code'))} | "
            f"{_display(_value(item, 'package_category'))} | "
            f"total {_display(_value(item, 'total_amount'), True)}"
        )
    document.line(f"TOTAL FINAL DA RETIRADA: {_display(final_total, True)}", bold=True)
    document.line(
        "Confirmo que retirei o pacote identificado neste comprovante e que o pagamento informado foi realizado.",
        bold=True,
    )
    document.signature(_value(withdrawal, "signature"))
    document.pdf.save()
    output.seek(0)
    return output
