# Identidade institucional Adelinha

O tema padrão é definido em `branding.py`: laranja `#ff4d00`, verde-água `#4db6ac`, grafite `#262626` e branco. Os valores foram escolhidos por referência visual à imagem da conversa; a extração exata por pixel e a inclusão da logo dependem do arquivo original, ainda não disponibilizado no ambiente.

O laranja identifica ações e destaques. O verde-água tem versões mais escuras para texto e fundos suaves para apoio. Botões, links e indicadores de foco usam combinações com contraste de pelo menos 4,5:1. Erros, alertas e confirmações mantêm suas cores operacionais.

A fonte Montserrat é servida localmente, inclusive nos PDFs novos, sem chamadas a Google Fonts no navegador. A fonte e a licença SIL Open Font License foram obtidas no repositório oficial `google/fonts`, diretório `ofl/montserrat`. Os arquivos Regular e Bold são instâncias estáticas dos pesos 400 e 700 da fonte variável original; a versão WOFF2 mantém os pesos variáveis.

## Logo original pendente

O código está preparado para servir `static/brand/adelinha-2026/logo-original.png` sem redesenhar, cortar ou esticar. Esse arquivo deve ser a arte original aprovada. Ele ainda não faz parte desta alteração: a imagem visível na conversa não ficou disponível como arquivo no ambiente. Enquanto isso, o cabeçalho sem imagem personalizada usa apenas o nome institucional em texto. Imagens já cadastradas no banco têm prioridade e são preservadas.

E-mails novos incorporam a logo original disponível como imagem CID, sem depender de um endereço externo. PDFs novos incluem a logo somente quando ela estava disponível na emissão, conforme o campo `document_logo_present`.

## Banners e personalização

O banner padrão ME GUARDE ganhou uma versão em verde-água, laranja e grafite, preparada a partir da arte anterior com a ferramenta de edição de imagem. Foi convertido para WebP sem perdas, preservando os pixels da versão adaptada; o arquivo fica abaixo do limite de 900 KB. O banner anterior permanece em `static/me-guarde-banner.webp`.

Nenhum upload do administrador, tema salvo, foto ou configuração existente é regravado. O banner adaptado aparece apenas quando não há imagem principal personalizada. Os demais banners continuam sendo geridos em Configurações → Banners. A opção “Restaurar cores padrão” passa a usar a nova paleta e não exclui temas salvos.

## Documentos e histórico

Cadastros e retiradas novos registram `document_brand_version`. Registros antigos permanecem sem versão e usam a apresentação histórica dos PDFs. Seus textos, assinaturas, datas, identificadores, valores e hashes não são recalculados. A existência da logo na emissão é registrada separadamente para não acrescentar uma imagem a um documento antigo quando a logo for disponibilizada depois.

Os recursos em `static/brand/adelinha-2026` e a entrada correspondente em `DOCUMENT_BRANDS` são versionados. Após a primeira emissão em produção, não os substitua: para outra revisão da identidade, crie outra pasta e outra entrada no registro de versões, mantendo as anteriores.

## Validação

Os testes cobrem restauração e personalização de temas, contraste, preservação de uploads, logo sem alterações, e-mail HTML com texto alternativo, incorporação CID e renderização histórica de documentos. Nenhum teste envia e-mail real.
