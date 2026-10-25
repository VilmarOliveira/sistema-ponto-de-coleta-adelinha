# Atualização na Oracle: banner, WhatsApp e abas de usuários

As alterações usam as imagens de `IMAGENS ATUALIZACAO.rar`, enviadas pelo proprietário:

- `static/me-guarde-banner.webp`: versão WebP sem perda do arquivo “Coração azul na caixa laranja.png”, mantendo 2170 × 725 pixels. Tamanho reduzido de 1.070.018 para 572.984 bytes; a comparação dos pixels decodificados apresentou diferença zero. Nenhum elemento foi redesenhado.
- `static/whatsapp-original.jpg`: cópia do JPG original de 554 × 554 pixels e 23.922 bytes. A transparência externa é aplicada na exibição com `clip-path: circle(50%)`; o branco dentro do símbolo permanece intacto. O número e o endereço de atendimento permanecem iguais.

Não há dependências novas nem migração de dados específica desta atualização. Os arquivos personalizados do banner continuam armazenados no banco, separados dos banners rotativos e do cabeçalho institucional. Nenhum cadastro, código ou histórico é regravado pela nova organização em abas.

## Procedimento

1. Envie as alterações deste checkout ao repositório e à branch usada pela instalação, após a revisão habitual. Na Oracle, faça o backup/snapshot do banco já previsto no procedimento de atualização. Preserve as variáveis existentes, incluindo `DATABASE_URL` e as credenciais.
2. Na pasta da instalação, execute `git status --short`. Se houver alterações locais, preserve-as antes de atualizar. Com o checkout limpo, execute:

   ```bash
   git pull --ff-only
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   python -m pip check
   env -u DATABASE_URL -u DATABASE -u TEST_DATABASE_URL python -m pytest -q
   ```

   Ajuste o caminho do ambiente virtual se a instalação usa outro nome. O último comando executa a suíte com SQLite temporário, sem usar o banco de produção; o teste opcional de PostgreSQL será pulado. Para incluí-lo, defina `TEST_DATABASE_URL` exclusivamente para um banco isolado de testes, como no CI.
3. Reinicie apenas o serviço web pelo gerenciador já utilizado. Exemplo, caso o serviço se chame `me-guarde`:

   ```bash
   sudo systemctl restart me-guarde
   sudo systemctl status me-guarde --no-pager
   ```

4. No domínio da instalação, confira `/health`: deve responder HTTP 200 com `{"status":"ok"}`. Abra a página inicial no computador e no celular. O banner deve aparecer inteiro abaixo do menu, e o WhatsApp deve abrir o atendimento existente. A nova versão do service worker atualiza o cache dos estilos; recarregue a página caso um navegador ainda mostre a versão anterior.
5. Em **Configurações → Banners**, confira a imagem. Se já havia um banner personalizado no banco, ele é preservado: substitua a imagem nessa tela se desejar outra arte. Recomendação atual: 2048 × 684 px, PNG/JPG/WebP, limite de 900 KB. O banner principal participa do carrossel com até três imagens ativas. A prévia permite conferir a imagem antes de salvar.
6. Em **Configurações → Usuários**, confira as abas **Clientes** e **Membros da equipe**, suas buscas, os botões de adicionar e as ações disponíveis. No celular, cada registro aparece como cartão. Somente os administradores com permissão de usuários (e o acesso administrativo legado enquanto habilitado) têm acesso a essa gestão; gerentes e atendentes mantêm as permissões operacionais existentes.

## Validação desta implementação

- 99 testes automatizados aprovados, incluindo PostgreSQL 16 isolado.
- Navegador Chromium em 1440, 390 e 320 pixels: banner completo, proporção original, ícone original com exterior transparente, sem transbordamento horizontal da página, buscas independentes, alternância das abas, formulário de equipe e upload/prévia/restauração do banner.
- No celular, o botão de WhatsApp fica oculto enquanto um campo de texto está em foco, para liberar espaço durante a digitação. O botão também fica oculto durante a sobreposição com campos ou botões; há espaço reservado ao final da página para alcançar as últimas ações.
- A instalação Oracle não foi acessada nem reiniciada por esta tarefa.
