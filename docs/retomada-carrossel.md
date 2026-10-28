# Retomada do carrossel

O carrossel preserva seu layout, bolinhas, gesto horizontal e transição. Setas e botão Pausar continuam ausentes. O intervalo é de 3.000 ms; um único banner permanece estático.

## Causa e correção

A implementação anterior mantinha flags de toque, hover e foco entre suspensões. Um toque interrompido pelo bloqueio ou pela troca de aba podia não receber `touchend`/`touchcancel`, deixando a rotação pausada. Também tratava foco de toque nas bolinhas como foco permanente de computador, e ouvia somente `visibilitychange` para a suspensão, sem reconciliar os estados em foco da janela, restauração de página e ciclo freeze/resume.

Agora há um único `setTimeout` encadeado, cancelado antes de qualquer reagendamento, com geração para invalidar callbacks antigos. Cada retomada mantém a imagem atual e começa um novo prazo de três segundos; não há reprodução de trocas perdidas. A suspensão limpa gestos interrompidos e hover transitório, e a retomada consulta a visibilidade, foco atual dos controles, capacidade de hover e posição do mouse. Qualquer novo movimento do mouse também reconcilia hover, mesmo se `pointerleave` tiver sido perdido.

Eventos tratados: `visibilitychange`, `freeze`, `resume`, `blur`/`focus` da janela e `pagehide`/`pageshow` (incluindo restauração de página). Um callback atrasado mais de 250 ms além do prazo é descartado e reagendado com três segundos completos, usando tanto relógio monotônico quanto relógio de parede, para cobrir suspensões que não entreguem eventos de ciclo de vida. Este mecanismo também pode adiar uma troca sob carga intensa de JavaScript; evita uma troca imediata na volta de uma suspensão silenciosa.

No computador, hover e foco nos controles pausam até terminarem. No celular, o toque pausa até o último dedo sair; cancelamento e suspensão encerram o gesto pendente. Foco de toque nas bolinhas não prende a reprodução; foco visível de teclado continua acessível e pausa. Movimento reduzido impede rotação automática, preservando bolinhas e setas do teclado para navegação manual. Ao desativá-lo, a rotação recomeça com prazo completo se nenhuma outra condição de pausa estiver ativa.

## Verificação

`tests/browser/carousel_resume.cjs`, com o servidor isolado em `tests/browser/serve_responsive.py`, verifica computador (1440 px) e celular (390 px): intervalo exato, prazo completo na retomada, aba oculta, foco da janela, pagehide/pageshow, freeze/resume, múltiplas notificações sem temporizadores duplicados, callback atrasado, hover e foco, perda de pointerleave, toque prolongado, swipe, toque interrompido, touchcancel, toque em bolinhas, movimento reduzido e navegação manual. Inclui suspensão real do JavaScript por CDP (`Debugger.pause`/`Debugger.resume`) no Chromium e caso com um único banner.

Troca de visibilidade, perda/retorno de foco e bloqueio/desbloqueio são simulados por eventos; a suspensão de JavaScript no Chromium é real via CDP. Minimização de janela de um navegador com interface, bloqueio físico do celular, aparelhos físicos e Safari/iOS não foram testados neste ambiente. Não se deve apresentar as simulações como validação física desses dispositivos.

Reprodução:

```bash
.venv/bin/python tests/browser/serve_responsive.py
# Em outro terminal, com Playwright instalado conforme tests/browser/README.md:
NODE_PATH=/tmp/adelinha-browser/node_modules node tests/browser/carousel_resume.cjs
```

Relatório: `/tmp/adelinha-carousel-results/report.json`. Os dados são fictícios, em banco temporário; nenhuma integração real é acionada.
