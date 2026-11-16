# Operação offline — contingência do ponto

Módulo integrado em /offline/, acessível pelo botão **Operação offline** na Área
do Ponto. Esta versão registra a operação física e sincroniza um diário para
conferência; não tenta reproduzir offline as validações financeiras ou contratuais
do servidor.

## Preparar e usar

1. Entrar na Área do Ponto com conta individual que tenha acesso a clientes,
   pacotes e retiradas. O login administrativo legado não prepara aparelhos.
2. Abrir Operação offline, conectado, e escolher senha local com pelo menos
   oito caracteres. Essa senha é diferente da senha do site.
3. Aguardar a confirmação de preparação. Manter o endereço /offline/ nos favoritos.
   Pode fechar e abrir novamente a página, inclusive sem internet, neste navegador.
4. Sem conexão, desbloquear com a senha local. Cadastrar clientes provisórios,
   receber pacotes ou registrar retiradas com documento, assinatura e valor
   manualmente conferido. Os identificadores OFF são temporários e não substituem
   os códigos oficiais CLTPCA, PCTPCA e CMPPCA.
5. Baixar um backup protegido ao concluir o atendimento. Guardar arquivo e senha
   em locais separados. O backup não contém a senha e não pode ser aberto sem ela.
6. Com conexão restabelecida, entrar online com o mesmo operador/ambiente, voltar
   ao módulo e usar Sincronizar agora. A sincronização é manual e não envia e-mails.
7. Abrir cada registro em Registros e conferência. Consultar os conflitos, concluir
   ou localizar a operação no fluxo online normal e vincular seu código oficial.
   O vínculo verifica correspondência do cliente, rastreio/cliente do pacote, ou
   documento, conjunto de pacotes e valor da retirada. O mesmo registro online não
   pode ser vinculado duas vezes.
8. Se o registro local estiver incorreto ou duplicado, informar o motivo e usar
   Não aplicar registro incorreto ou duplicado. O histórico permanece no servidor
   e nenhum dado operacional online é alterado.
9. Atualizar dados para preparar o próximo atendimento. Remover dados locais
   somente após todos os registros estarem conferidos, com backup preservado.

## Regras e limites

- Preparação válida por sete dias. Após esse período pode ler, fazer backup e
  sincronizar, mas deve atualizar online antes de criar novas operações.
- A primeira preparação exige internet e servidor funcionando. Abrir o site pela
  primeira vez durante uma queda não cria uma cópia offline.
- Não é uma cópia completa do banco. Prepara clientes ativos (nome, telefone e
  código, sem CPF/e-mail/senhas) e pacotes ainda não retirados. Acima de 10 mil
  clientes ou pacotes, a preparação é recusada para evitar corte silencioso.
- Novos clientes são pré-cadastros: nenhum contrato é aceito e nenhuma identidade
  é validada automaticamente. O cadastro oficial e suas validações continuam online.
- Peso, dimensões, rastreio e prateleira são exigidos. Limite: soma até 150 cm e
  peso até 20 kg. Classificação de tamanho é local; valor/cobertura são conferidos
  online, inclusive créditos do plano e diárias.
- Retirada local exige assinatura e confirmação humana do documento e valor.
  Dinheiro e Conferência manual são as modalidades locais; nenhuma chamada Pix,
  cobrança, confirmação de API ou consumo de crédito acontece offline.
- A sincronização guarda o diário em offline_operations, separado dos cadastros,
  pacotes e comprovantes oficiais. **Enviado não significa aplicado.** Não há
  importação automática para clients, packages, pickups ou o livro de créditos.
  A conferência no fluxo normal é necessária para manter suas validações.
- Reenvio do mesmo identificador/conteúdo é idempotente. Conteúdo alterado com
  identificador antigo é recusado sem alterações parciais no lote.
- Mudanças em pacotes e duplicidade de rastreios são sinalizadas. Aparelhos não
  conversam entre si sem internet; evite atender o mesmo pacote em dois aparelhos.
- Escritas concorrentes de abas são recusadas por versão, preservando a gravação
  mais recente. Fechar a aba antiga e reabrir com a senha atualiza a visão.
- Sincronizar e conferir exige sessão atual e permissões atuais. Operador ou
  ambiente diferente é recusado. Revogar acesso online impede novas sincronizações,
  mas não apaga uma cópia local que já foi preparada.

## Proteção e recuperação

IndexedDB guarda um envelope cifrado com AES-GCM; a chave é derivada da senha por
PBKDF2/SHA-256 (310 mil iterações e salt aleatório). A senha e os tokens de sessão
não são gravados nesse envelope. Bloqueio manual e por 15 minutos de inatividade
removem dados e chave da memória da tela. O aparelho deve ter bloqueio de tela.

O navegador pode remover armazenamento local, especialmente em modo privado ou
quando falta espaço. A aplicação pede armazenamento persistente, mas isso não é
garantia; faça backups. Erros de quota/gravação são exibidos e a interface só
confirma um registro depois de concluir a transação local.

Para restaurar: abrir o mesmo domínio conectado, sem outra base local nesse
navegador, escolher Restaurar backup protegido e informar a senha local. Não
substitui uma base já existente. Origem/domínio, ambiente, banco e operador são
isolados; não importar dados de testes na produção. Troca de domínio ou SECRET_KEY
exige planejamento para migrar registros pendentes, não edição manual do backup.

O service worker tem escopo /offline/ e só guarda HTML/CSS/JS genéricos. Não guarda
respostas de API nem páginas pessoais. O cache público existente preserva esse
cache separado. Não muda autenticação, domínio, banco ou provedor de produção.

## Instalação em testes

Após integrar o PR em develop, executar no servidor:

~~~bash
cd /home/ubuntu/sistema-ponto-de-coleta-adelinha-teste
git pull --ff-only origin develop
sudo systemctl restart ponto-coleta-teste.service
sudo systemctl is-active ponto-coleta-teste.service
~~~

As tabelas do diário são criadas na inicialização, sem alterar dados existentes.
Não precisa de novo banco, nova instância Oracle ou novas chaves Google/Pix.
Nenhuma atualização de produção deve ser presumida: validar o módulo em testes
antes de promover o código para main e instalar na produção.
