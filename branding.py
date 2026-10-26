"""Identidade Adelinha: paleta, contraste e recursos versionados compartilhados.

A paleta foi escolhida por referência visual; a medição da arte original está
pendente do arquivo-fonte. Recursos de documentos emitidos não devem ser alterados.
"""
from functools import lru_cache
from pathlib import Path

# Recursos já usados em documentos são imutáveis; novas revisões ganham outra chave.
DOCUMENT_BRANDS = {
    'adelinha-2026': {'orange': '#ff4d00', 'teal': '#4db6ac', 'text': '#262626',
                      'asset_root': Path(__file__).parent / 'static' / 'brand' / 'adelinha-2026'},
    'adelinha-turquesa-2026': {'orange': '#ff4d00', 'teal': '#00ced1', 'text': '#262626',
        'asset_root': Path(__file__).parent / 'static' / 'brand' / 'adelinha-turquesa-2026',
        'font_root': Path(__file__).parent / 'static' / 'brand' / 'adelinha-2026'},
}
BRAND_VERSION = 'adelinha-turquesa-2026'
CURRENT_BRAND = DOCUMENT_BRANDS[BRAND_VERSION]
ASSET_ROOT = CURRENT_BRAND['asset_root']
# Usar somente o arquivo original aprovado, sem recriar a marca institucional.
ORIGINAL_LOGO = ASSET_ROOT / 'logo-original.png'
ORANGE = CURRENT_BRAND['orange']
TEAL = CURRENT_BRAND['teal']
GRAPHITE = CURRENT_BRAND['text']
WHITE = '#ffffff'
DEFAULT_THEME = {
    'primary': ORANGE, 'secondary': TEAL, 'page': WHITE, 'surface': WHITE,
    'text': GRAPHITE, 'link': '#00676b', 'border': '#b8e7e8', 'header': WHITE,
    'footer': GRAPHITE, 'button': ORANGE, 'button_hover': '#c23800',
}


def luminance(color):
    values = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    values = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values]
    return sum(value * weight for value, weight in zip(values, (.2126, .7152, .0722)))


def contrast(first, second):
    values = (luminance(first), luminance(second))
    return (max(values) + .05) / (min(values) + .05)


def readable_text(background):
    if contrast(GRAPHITE, background) >= 4.5:
        return GRAPHITE
    return max((WHITE, '#000000'), key=lambda color: contrast(color, background))


def accessible_accent(color, background=WHITE):
    """Preserva a cor de apoio, escurecendo apenas sua versão de texto."""
    rgb = [int(color[i:i+2], 16) for i in (1, 3, 5)]
    for step in range(101):
        candidate = '#' + ''.join(f'{round(value * (1 - step / 100)):02x}' for value in rgb)
        if contrast(candidate, background) >= 4.5:
            return candidate
    return readable_text(background)


def theme_variables(theme=None):
    colors = {**DEFAULT_THEME, **(theme or {})}
    return {
        '--orange': colors['primary'], '--orange-dark': colors['button_hover'],
        '--orange-ink': accessible_accent(colors['primary'], colors['surface']),
        '--brand-teal': colors['secondary'],
        '--teal': accessible_accent(colors['secondary'], '#d1f2f3'),
        '--teal-dark': colors['link'], '--ink': colors['text'],
        '--muted': '#526365', '--green': '#116843', '--page': colors['page'], '--surface': colors['surface'],
        '--line': colors['border'], '--footer': colors['footer'],
        '--theme-header': colors['header'], '--theme-link': colors['link'],
        '--theme-button': colors['button'], '--button-ink': readable_text(colors['button']),
        '--button-hover-ink': readable_text(colors['button_hover']),
        '--footer-ink': readable_text(colors['footer']),
        '--teal-soft': '#eafafa', '--teal-soft-hover': '#d1f2f3',
        '--cream': '#fff5ef', '--focus-ring': colors['link'],
    }


def default_stylesheet():
    declarations = ';'.join(f'{name}:{value}' for name, value in theme_variables().items())
    return (f":root{{{declarations}}}\n"
            "@font-face{font-family:Montserrat;src:url('/static/brand/adelinha-2026/Montserrat.woff2') format('woff2');font-style:normal;font-weight:100 900;font-display:swap}\n")


@lru_cache(maxsize=None)
def pdf_fonts(version=BRAND_VERSION):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    brand = DOCUMENT_BRANDS[version]
    root = brand.get('font_root', brand['asset_root'])
    normal, bold = f'{version}-Montserrat', f'{version}-Montserrat-Bold'
    for name, filename in ((normal, 'Montserrat-Regular.ttf'), (bold, 'Montserrat-Bold.ttf')):
        pdfmetrics.registerFont(TTFont(name, str(root / filename)))
    return normal, bold
