"""Persistent card images; derivatives are generated once, on upload."""
from io import BytesIO
from PIL import Image, ImageOps

DEFAULT_CARDS = (
    (1, 'Cadastre-se', 'Acesse a Área do Cliente.', 'person'),
    (2, 'Use nosso endereço', 'Na loja, escolha um novo endereço de entrega.', 'location'),
    (3, 'Identifique seu pacote', 'Use nome completo e código.', 'edit'),
    (4, 'Aguarde e retire', 'Confira o endereço do ponto e finalize a compra.', 'save'),
)


def optimized_versions(data):
    with Image.open(BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source)
        image.seek(0)
        image = image.convert('RGBA' if 'A' in image.getbands() or 'transparency' in image.info else 'RGB')
        dimensions = image.size
        versions = []
        for size in ((320, 480), (640, 960)):
            thumb = image.copy()
            thumb.thumbnail(size, Image.Resampling.LANCZOS)
            output = BytesIO()
            thumb.save(output, 'WEBP', quality=92, method=6)
            versions.append(output.getvalue())
        return dimensions, versions
