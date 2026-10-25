from datetime import date

import pytest

from core import (
    calculate_discount, calculate_fees, classify_package, package_arrival_message,
    pix_payload, valid_cpf, validate_surcharge,
)


def test_pix_limits_long_holder_name_to_emv_standard():
    payload = pix_payload("38145273000105", "AMOR INFINITO MARKETING E SOLUCOES EMPRESARIAIS", 5)
    assert "5925AMOR INFINITO MARKETING" in payload
    assert "SOLUCOES EMPRESARIAIS" not in payload


@pytest.mark.parametrize("cpf", ["52998224725", "529.982.247-25", "98765432100"])
def test_valid_cpf_accepts_plain_or_formatted_value(cpf):
    assert valid_cpf(cpf)


@pytest.mark.parametrize("cpf", ["", "123", "11111111111", "52998224724", "abc"])
def test_valid_cpf_rejects_bad_length_repeated_and_wrong_check_digits(cpf):
    assert not valid_cpf(cpf)


def test_package_arrival_message_preserves_lines_accents_and_brazilian_value():
    message = package_arrival_message("Maria da Silva", "PCT-000123", "BR001234", 5)
    assert message == (
        "Olá, Maria da Silva! 😊\n\n"
        "Seu pacote PCT-000123, com rastreio BR001234, chegou ao Ponto de Coleta Adelinha!\n\n"
        "O valor do serviço de armazenamento é de R$ 5,00. Você tem 4 dias corridos para retirar, "
        "contando hoje como o primeiro dia.\n\n"
        "A partir do 5º dia, será cobrada uma taxa adicional de R$ 0,50 por dia, por pacote, até a retirada.\n\n"
        "Agradecemos pela compreensão!"
    )
    assert "R$ 10,00" in package_arrival_message("João", "PCT-2", "00001", 10)


def test_discount_by_value_and_percentage_rounds_to_two_decimals():
    assert tuple(map(str, calculate_discount(10, "2,50", ""))) == ("valor", "2.50", "2.50", "10.00", "7.50")
    assert tuple(map(str, calculate_discount(10, "", "12,5"))) == ("porcentagem", "12.5", "1.25", "10.00", "8.75")
    assert tuple(map(str, calculate_discount(5, "", "100")))[-1] == "0.00"


@pytest.mark.parametrize(("amount", "percent"), [("1", "10"), ("5.01", ""), ("", "100.01"), ("NaN", "")])
def test_invalid_discount_is_rejected(amount, percent):
    with pytest.raises(ValueError):
        calculate_discount(5, amount, percent)


def test_surcharge_requires_reason_and_two_decimal_non_negative_amount():
    assert tuple(map(str, validate_surcharge("2,50", "Embalagem reforçada"))) == ("2.50", "Embalagem reforçada")
    assert tuple(map(str, validate_surcharge("0,00", ""))) == ("0.00", "None")
    for amount, reason in (("1", ""), ("-1", "Motivo"), ("1.001", "Motivo"), ("NaN", "Motivo")):
        with pytest.raises(ValueError):
            validate_surcharge(amount, reason)


@pytest.mark.parametrize("dimensions,weight,expected", [
    ((30, 25, 25), 10, ("Pequeno", 4.9)),
    ((30, 25, 25.01), 10, ("Grande", 9.9)),
    ((50, 50, 50), 20, ("Grande", 9.9)),
])
def test_category_boundaries(dimensions, weight, expected):
    assert classify_package(*dimensions, weight) == expected


@pytest.mark.parametrize("dimensions,weight", [
    ((50, 50, 50.01), 20),
    ((10, 10, 10), 20.01),
    ((0, 10, 10), 1),
])
def test_rejected_packages(dimensions, weight):
    with pytest.raises(ValueError):
        classify_package(*dimensions, weight)


def test_calendar_day_fees_and_pickup_freeze():
    notice = "2026-09-10T10:00:00-03:00"
    assert calculate_fees(5, notice, today=date(2026, 9, 13))["late_fee"] == 0
    assert calculate_fees(5, notice, today=date(2026, 9, 14))["late_fee"] == .5
    assert calculate_fees(5, notice, today=date(2026, 9, 16))["late_fee"] == 1.5
    frozen = calculate_fees(5, notice, "2026-09-14T19:00:00-03:00", today=None)
    assert frozen["total"] == 5.5


def test_pix_payload_has_key_amount_and_valid_crc():
    payload = pix_payload("38145273000105", "Recebedor Teste", 15.50)
    assert payload.startswith("000201")
    assert "38145273000105" in payload
    assert "540515.50" in payload
    assert payload[-8:-4] == "6304"
    assert len(payload[-4:]) == 4


def test_pix_enforces_merchant_byte_limit_and_crc():
    import binascii
    payload = pix_payload('a' * 77, 'Titular', 4.9)
    assert '2699' in payload
    assert payload[-4:] == f'{binascii.crc_hqx(payload[:-4].encode(), 0xFFFF):04X}'
    with pytest.raises(ValueError):
        pix_payload('a' * 78, 'Titular', 4.9)
    with pytest.raises(ValueError):
        pix_payload('não-ascii', 'Titular', 4.9)
