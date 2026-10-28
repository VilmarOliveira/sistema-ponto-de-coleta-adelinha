# Cartões explicativos

Administração: Área do Ponto → Configurações → Cartões explicativos. Apenas o administrador (incluindo o acesso administrativo legado) pode abrir ou salvar esta configuração. Há quatro posições fixas, com salvamento individual de título, texto alternativo e imagem. A seção ocupa o antigo local de “Como funciona”, antes das lojas favoritas, sem repetir os três cartões antigos nem duplicar os quatro novos. Cancelar recarrega os valores persistidos; nenhuma alteração é enviada.

O repositório disponível continha quatro ícones vetoriais nesta seção, não quatro artes fotográficas/verticais. Esses mesmos desenhos foram preservados como imagens iniciais, sem inventar artes substitutas. Os títulos iniciais são Cadastre-se, Use nosso endereço, Identifique seu pacote e Aguarde e retire. Se a instalação em produção tiver outras quatro artes fora do repositório, elas deverão ser fornecidas/importadas pelo painel.

Cada envio aceita PNG, JPEG ou WebP reais, com até 921.600 bytes (900 KB). A recomendação de 800 × 1200 px / 2:3 não restringe a proporção aceita. A validação existente do navegador verifica tamanho, assinatura e decodificação; o servidor verifica novamente o conteúdo, e só salva após gerar as duas versões. Uma falha mantém também os títulos e textos alternativos persistidos anteriores. Os valores digitados de texto continuam disponíveis na tela para correção.

A tabela `explanatory_cards` mantém quatro registros, o original, duas miniaturas WebP (qualidade 92, até 320 × 480 e 640 × 960), dimensões, título, descrição e hash da imagem. A inicialização cria somente estruturas/registros ausentes e nunca sobrescreve personalizações existentes. Os blobs ficam no banco já utilizado pelo sistema, seguindo seus backups e persistência; nenhum arquivo de upload depende do diretório temporário ou do disco de um contêiner.

A página consulta somente metadados. A seleção da miniatura é feita por `picture`/`source`; ambas são carregadas sob demanda. A moldura 2:3 reserva espaço e `object-fit: contain` preserva toda a imagem, centralizada e sem margens CSS adicionais. Títulos, início das molduras e links ficam alinhados em cada linha, mesmo com títulos de tamanhos diferentes. Há quatro colunas em telas amplas, duas no tablet e uma no celular. Os ícones iniciais são SVGs pequenos, independentes da resolução. O original é solicitado apenas ao abrir o diálogo; sem suporte a diálogo/JavaScript, o link abre diretamente a imagem. A versão SHA-256 da imagem compõe a URL, com cache público imutável, ETag e atualização automática na substituição. URLs antigas redirecionam para a versão atual antes de retornar conteúdo novo.

A ampliação utiliza diálogo modal nativo com nome acessível, foco no botão Fechar, Tab/Shift+Tab contidos, Escape, clique/toque fora da imagem e retorno de foco ao cartão. A indicação muda entre Clique e Toque por capacidade de ponteiro. Nenhuma regra de carrossel, Pix, pagamentos ou documentos foi alterada.

## Verificação

- Testes funcionais de formato real, imagens de diferentes proporções, limite exato e excesso de um byte, conteúdo corrompido, salvamento atômico, cancelamento, edição sem imagem, atualização de cache, reinicialização e permissões (inclusive gerente com sinalizador de configurações habilitado).
- Teste Chromium com Playwright em 320, 360, 390, 430, 768, 1024 e 1440 px: tela administrativa sem rolagem lateral; upload, prévia, erros e cancelamento; imagem publicada sem deploy; seleção de miniaturas e ausência de solicitação do original até interação; ampliação, foco, teclado e toque.
- Servidor de testes com SQLite temporário e dados fictícios, sem mensagens reais; teste adicional de persistência em PostgreSQL temporário.
- Dispositivos físicos e Safari/iOS não foram testados. A preservação das quatro ilustrações refere-se ao conteúdo encontrado no repositório.

Reprodução: iniciar o servidor de [fixtures](../tests/browser/README.md), então executar `NODE_PATH=/tmp/adelinha-browser/node_modules node tests/browser/explanatory_cards.cjs`. Capturas são salvas em `/tmp/adelinha-card-results`.
