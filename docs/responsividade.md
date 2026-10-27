# Revisão da responsividade

O sistema continua usando os mesmos endereços, templates, dados e permissões em computador, tablet e celular. A paleta e os recursos da identidade visual não foram alterados.

## Organização dos estilos

`static/style.css` mantém estilos de componentes e documentos. As antigas regras de tela conflitantes foram retiradas dele; `static/responsive.css` concentra os ajustes de tela e usa grades fluidas, espaçamentos compartilhados e duas faixas de adaptação. As regras de impressão continuam separadas dos ajustes de tela.

O cabeçalho usa a largura real das opções de navegação, da marca e do nome do usuário para escolher entre navegação completa e botão Menu. Em telas pequenas, marca e Menu ficam na mesma linha e centralizados verticalmente. O nome do usuário quebra linha e não é substituído por reticências. Escape fecha o menu e retorna o foco ao botão.

## Componentes corrigidos

- Cartões, grupos de campos, ações, títulos, mensagens, rodapé e estados vazios se ajustam ao espaço disponível. Campos têm fonte de 16 px e botões/indicadores têm alvos de pelo menos 44 px.
- Campos de assinatura mantêm o bitmap e os valores originais ao redimensionar, usando a proporção natural da área de desenho. Rascunhos de assinatura antigos são ajustados sem esticar a imagem. Eventos de ponteiro permitem mouse, dedo e caneta; a captura do ponteiro evita perder o traço ao sair da borda. O redimensionamento não redefine `canvas.width` ou `canvas.height`.
- Usuários são apresentados como cartões em telas pequenas, com todos os dados e ações. Tabelas que precisam manter colunas usam uma região identificada e com rolagem horizontal própria, acessível pelo teclado.
- QR Code e Pix Copia e Cola ficam dentro do contêiner. O código usa quebra visual suave, sem acrescentar caracteres ao valor copiado.
- Logos e banners usam proporção preservada. O carrossel mantém o intervalo de três segundos, os indicadores e o toque, sem setas ou botão Pausar.
- O WhatsApp respeita áreas seguras, tem espaço reservado no fim da página e é ocultado quando encobrir texto, imagem, campo ou ação. Em telas menores também é ocultado durante o foco em campos.
- Os renderizadores de PDF e os dados históricos não foram alterados. A impressão do site mantém o formato documental, sem as adaptações de tela.

## Verificação realizada

A matriz de Chromium passou por **752 cenários**, em **320, 360, 390, 430, 768, 1024 e 1440 px**, além da rotação para 932 × 430 px, cobrindo 53 combinações de perfil/fluxo em 47 endereços/estados de teste. Foram incluídos usuários anônimos e autenticados, menus e edições abertos, dados longos, erros, sucesso e estados vazios. Nenhum dos cenários apresentou rolagem horizontal da página, campos fora da tela ou sobreposição entre marca e navegação.

As verificações adicionais passaram: assinatura por toque e por mouse preservada na rotação; campos e seleção da retirada, confirmação de pagamento e Pix preservados; carrossel; posicionamento do WhatsApp; impressão; PDFs; contêiner de logo quadrada. O QR Code e a cópia exata do Pix também foram verificados na matriz.

A suíte funcional existente passou com **131 testes**, com três testes opcionais de PostgreSQL não executados nesta revisão de interface. As alterações não modificam consultas, migrações ou integrações de servidor.

Os scripts, critérios e instruções para reprodução estão em [tests/browser/README.md](../tests/browser/README.md). O limite pendente é a validação em aparelhos físicos e Safari/iOS; a matriz foi executada por emulação no Chromium.
