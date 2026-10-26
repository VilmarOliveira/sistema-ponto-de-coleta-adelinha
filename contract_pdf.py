"""Cópia PDF do contrato histórico aceito."""
import base64, textwrap
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

def build_contract_pdf(client):
    out=BytesIO(); pdf=canvas.Canvas(out,pagesize=A4); width,height=A4; y=height-45
    def line(text,bold=False):
        nonlocal y
        for wrapped in textwrap.wrap(str(text),100) or ['']:
            if y<60: pdf.showPage(); y=height-45
            pdf.setFont('Helvetica-Bold' if bold else 'Helvetica',9); pdf.drawString(45,y,wrapped); y-=12
    line('PONTO DE COLETA ADELINHA — CONTRATO ASSINADO',True)
    code = client["contract_public_id"] if "contract_public_id" in client.keys() else None
    code = code or client["public_id"]
    line(f"Contratante: {client['name']} | CPF: {client['cpf']} | Código: {code}")
    line(f"Versão: {client['terms_version']} | Aceite: {client['accepted_at']}")
    for paragraph in (client['terms_text'] or 'Texto histórico não registrado').splitlines(): line(paragraph, paragraph[:2].rstrip('.').isdigit() or paragraph.isupper())
    if y<150: pdf.showPage(); y=height-45
    line('Assinatura registrada:',True)
    signature=client['signature']
    if signature and signature.startswith('data:image/png;base64,'):
        pdf.drawImage(ImageReader(BytesIO(base64.b64decode(signature.split(',',1)[1]))),45,y-95,width=260,height=90,preserveAspectRatio=True)
    else: line('Não registrado')
    pdf.save(); out.seek(0); return out
