import io
import sqlite3

import pytest
from PIL import Image

from app import IMAGE_UPLOAD_MAX_BYTES, create_app
from test_customization import csrf, legacy_login


@pytest.mark.parametrize('path,field,fields,table,column,identity', [
    ('/painel/configuracoes/identidade', 'image', {}, 'settings', 'header_image', 'id=1'),
    ('/painel/configuracoes/fotos', 'image', {'kind': 'Fachada', 'alt_text': 'Foto atual', 'position': '1'}, 'site_photos', 'image', 'position=1'),
    ('/painel/blog', 'cover_image', {'title': 'Artigo atual', 'slug': 'limite-imagem', 'summary': 'Resumo', 'body': 'Texto', 'action': 'draft'}, 'blog_posts', 'cover_image', "slug='limite-imagem'"),
])
def test_all_image_uploads_accept_900_kb_and_preserve_image_on_invalid_upload(tmp_path, path, field, fields, table, column, identity):
    database = str(tmp_path / 'uploads.db')
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test', 'DATABASE': database})
    client = app.test_client()
    legacy_login(client)
    image = io.BytesIO()
    Image.new('RGB', (2048, 684), 'orange').save(image, 'PNG')
    content = image.getvalue()
    content += b'\0' * (IMAGE_UPLOAD_MAX_BYTES - len(content))
    def upload(data, extra=None):
        return client.post(path, data={**fields, **(extra or {}), field: (io.BytesIO(data), 'imagem.png'), 'csrf_token': csrf(client)}, follow_redirects=True)
    result = upload(content)
    assert result.status_code == 200
    with sqlite3.connect(database) as db:
        before = db.execute(f'SELECT * FROM {table} WHERE {identity}').fetchone()
        assert db.execute(f'SELECT {column} FROM {table} WHERE {identity}').fetchone()[0] == content
    # Preserva também descrição, título e ordem ao rejeitar o arquivo.
    extra = {'alt_text': 'Não salvar', 'title': 'Não salvar'}
    if table == 'site_photos':
        extra['photo_id'] = '1'
    for bad in (content + b'0', b'\x89PNG\r\n\x1a\nINVALIDO', b'GIF89a', b''):
        result = upload(bad, extra)
        assert result.status_code in (200, 400)
        assert '900 KB' in result.text and 'imagem anterior foi preservada' in result.text
        with sqlite3.connect(database) as db:
            assert db.execute(f'SELECT * FROM {table} WHERE {identity}').fetchone() == before
    page = client.get(path).text
    assert 'data-max-bytes="921600"' in page
    assert 'Tamanho máximo: 900 KB por imagem.' in page
    assert 'Medidas recomendadas:' in page
