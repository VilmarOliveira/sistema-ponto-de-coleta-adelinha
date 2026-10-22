import re

import pytest

from receipt_pdf import build_receipt_pdf


SIGNATURE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="


def withdrawal(payment_method="Pix", reason="Serviço adicional"):
    return {
        "package_public_id": "PCT-000001",
        "snapshot_client_name": "Cliente Histórico",
        "snapshot_client_public_id": "ADL-000001",
        "receiver_name": "Pessoa que retirou",
        "document_type": "CPF",
        "receiver_document": "52998224725",
        "picked_at": "2026-10-15T15:30:00-03:00",
        "service_amount": 5,
        "late_days": 2,
        "late_amount": 1,
        "surcharge_amount": 2,
        "surcharge_reason": reason,
        "final_total": 6,
        "total_paid": 6,
        "payment_method": payment_method,
        "signature": SIGNATURE,
        # Dados históricos preservados, mas deliberadamente omitidos da apresentação.
        "original_total": 8,
        "discount_type": "valor",
        "discount_input": 2,
        "discount_amount": 2,
        "discount_applied_by": "staff",
        "surcharge_applied_by": "staff",
        "payment_confirmed": 1,
        "payment_confirmed_by": "staff",
        "staff": "staff",
    }


def package(number=1, tracking="BR001"):
    return {
        "package_public_id": f"PCT-{number:06d}",
        "tracking_code": tracking,
        "package_category": "Pequeno",
        "total_amount": 6,
    }


@pytest.mark.parametrize("payment_method", ["Pix", "Dinheiro"])
def test_pdf_uses_historical_final_total_and_requested_field_order(payment_method):
    content = build_receipt_pdf(withdrawal(payment_method), [package()], "Endereço do ponto").getvalue()
    expected = [
        b"Comprovante: CMPPCA-", b"Rastreio registrado:", b"Categoria registrada:",
        b"Aviso de chegada registrado:", b"Cliente registrado na retirada:", b"Data e hora:",
        b"Quem retirou: Pessoa que retirou", b"Documento: CPF 52998224725",
        b"Valor base deste pacote:", b"Dias de atraso: 2", b"Taxa de atraso: R$ 1,00",
        b"Acr", b"Motivo do acr", b"Desconto aplicado:", b"Total final pago: R$ 6,00",
        f"Tipo de Pagamento: {payment_method}".encode(),
    ]
    # ReportLab preserva as palavras ASCII no stream não comprimido; caracteres
    # acentuados usam a codificação da fonte e são cobertos pelos testes HTTP existentes.
    positions = [content.index(fragment) for fragment in expected]
    assert positions == sorted(positions)
    for removed in (b"Valor deste pacote antes", b"aplicado por", b"Total original",
                    b"Modalidade do desconto", b"Valor/percentual", b"Desconto calculado",
                    b"Desconto autorizado", b"Pagamento confirmado", b"Atendente:"):
        assert removed not in content
    assert b"/Subtype /Image" in content


def test_pdf_wraps_long_text_and_adds_pages_without_losing_packages():
    long_reason = "Motivo detalhado " * 80
    packages = [package(number, f"RASTREIO{number:03d}") for number in range(1, 61)]
    content = build_receipt_pdf(withdrawal("Dinheiro", long_reason), packages, "Endereço do ponto").getvalue()

    assert len(re.findall(rb"/Type /Page\b", content)) >= 2
    assert b"PCT-000001" in content
    assert b"Total final pago: R$ 6,00" in content
