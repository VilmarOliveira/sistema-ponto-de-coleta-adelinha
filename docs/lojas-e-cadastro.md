# Faixa de lojas e cadastro no cabeçalho

A página inicial apresenta as 16 lojas solicitadas como exemplos de onde comprar, sem links comerciais, afirmações de parceria ou patrocínio. O destinatário fictício foi removido. Os textos institucionais da solicitação acompanham as marcas.

Os arquivos são locais em `static/store-logos`. SVGs foram mantidos quando disponíveis em tamanho adequado; os rasters foram otimizados em WebP sem perda. O conjunto soma aproximadamente 142 KB. Apenas margens externas vazias dos rasters e o enquadramento do SVG Carrefour foram ajustados para equilibrar a escala, preservando a marca, cores e proporções. As variantes brancas de TikTok Shop, Renner e Centauro usam fundos de contraste apropriados. A fonte pública, revisão e hash de cada arquivo de origem estão registrados em `sources.json`; as marcas continuam pertencendo aos respectivos titulares. Sites oficiais bloquearam o acesso deste ambiente; foram usados os arquivos das marcas disponíveis em espelhos públicos, sem desenhar logos substitutas. O README de identidade do espelho AvantaLab documenta as fontes oficiais de Mercado Livre e TikTok Shop. Os SVGs foram inspecionados para não conter scripts, eventos ou referências a recursos remotos.

A faixa possui duas cópias de largura idêntica e percorre exatamente a largura de uma sequência a cada 65 segundos, sempre da direita para a esquerda. Não há seta nem instrução de movimento. A cópia visual fica oculta da tecnologia assistiva. Mouse sobre a faixa ou foco de teclado pausam o movimento; sair retoma a mesma posição. Movimento reduzido desativa a animação e apresenta todas as marcas em grade estática, sem depender de rolagem lateral. A máscara nas extremidades suaviza a entrada e saída, e apenas o contêiner da faixa recorta o conteúdo móvel.

O botão de cadastro utiliza a sessão Flask: não é renderizado para clientes ou equipe autenticados, em nenhuma página do template compartilhado. Visitantes veem um único botão: junto da Área do Cliente na navegação completa, ou ao lado do Menu no cabeçalho compacto. As duas posições compartilham a mesma condição de sessão; CSS mantém apenas uma visível, inclusive com o menu aberto. A marca institucional preserva sua proporção. O laranja do botão possui contraste com texto branco e o ícone é vetorial.

O endereço `/#cadastro` funciona tanto na página inicial quanto em outras páginas. Navegação com fragmento é respeitada pela restauração de rolagem existente. O formulário, seus dados e assinaturas, login, logout, permissões e integrações não foram alterados.

## Verificação

`tests/browser/stores_signup.cjs` usa o servidor isolado descrito em `tests/browser/README.md`: páginas inicial, dúvidas, blog e acesso/área autenticada, com visitante, cliente e administrador em 320, 360, 390, 430, 768, 1024 e 1440 px. Verifica CTA visível/ausente, menu aberto, alinhamento e ausência de sobreposição/rolagem lateral, destino do cadastro a partir de outra página, reaparecimento após logout, decodificação das 16 imagens, pausa por mouse/foco, continuidade geométrica da faixa e movimento reduzido.

Os testes usam banco temporário, credenciais fictícias e não enviam mensagens reais. Chromium com emulação de toque; aparelhos físicos e Safari/iOS não foram testados. Nenhuma migração de banco ou nova dependência de produção é necessária.
