# Atendimento offline integrado

Abrir /offline/ pela Área do Ponto. A preparação e a sincronização exigem conta
individual com permissões de clientes, pacotes e retiradas. Funciona inicialmente
no navegador do PC preparado, com senha local e backup cifrado. Preparar antes da
queda; a primeira abertura exige conexão. A preparação vale sete dias.

## Atendimento

- Cadastro com nome, CPF, telefone, e-mail, endereço residencial completo,
  leitura do contrato preparado, aceite e assinatura. E-mail e senha do cliente
  são validados online: registros novos ficam pendentes até essa etapa. O botão
  Concluir validação do cadastro online abre o formulário com os dados preenchidos.
  Não há login Google neste módulo, nem senha de cliente salva no PC.
- Clientes preparados incluem identificação, contato, endereço e dados do plano,
  protegidos no armazenamento local; senhas e tokens não são baixados.
- Recebimento com cliente, rastreio único, prateleira, medidas, peso e classificação.
  Limites iguais ao online: 80 cm/10 kg para Pequeno, 150 cm/20 kg para Grande.
  A previsão do plano desconta localmente os créditos dos recebimentos pendentes.
- Aviso de chegada explícito, iniciando o prazo na data original e preservando
  avisos existentes. Não envia mensagens sem conexão.
- Retirada com seleção de pacotes, identificação e assinatura do recebedor.
  Resumo: pacotes e diárias, acréscimo com motivo, desconto em valor ou porcentagem
  e total. O dia do aviso conta nos quatro dias gratuitos; atraso de R$ 0,50/dia.
  Pré-pagamentos preparados reduzem o saldo; o servidor revalida tudo ao importar.
- Duas opções de pagamento: **Pix AI** e **Dinheiro**. Em Dinheiro pode informar
  transferência ou outro meio na observação; a classificação permanece Dinheiro.
  O texto é preservado no online e no comprovante/PDF.
- Pix AI gera QR Code e copia e cola no próprio PC com a chave/titular preparados
  e o total calculado. Biblioteca QR vendorizada, sem CDN ou chamada FastFlow.
  O atendente confere o crédito no banco; o aplicativo bancário precisa de conexão
  para pagar. Não há confirmação por API. Valor zero não gera Pix.
- Lista de pacotes, busca por cliente/código/rastreio, avisos, saldo, histórico das
  últimas 100 retiradas online preparadas e impressão de comprovante local.
  Códigos OFF são provisórios até a sincronização; depois aparecem os oficiais.

## Sincronização

Clicar Sincronizar agora, conectado e autenticado com o mesmo operador/ambiente.
O diário é primeiro guardado idempotentemente em offline_operations. Depois o
servidor incorpora os registros compatíveis às tabelas operacionais:

1. Vincula cliente já validado com mesmo CPF/nome. Novo cliente ou divergência
   exige conclusão do cadastro online e nova tentativa.
2. Cria pacote oficial com data original, revalida exigências do cliente e aplica
   os créditos pela mesma função do sistema online. Diferença de cobertura gera
   conflito e desfaz a criação e o consumo daquele registro.
3. Registra o aviso, preservando a data original e sem reiniciar prazo existente.
4. Cria retirada, itens e comprovante com assinatura, data original, valores,
   modalidade, observação e responsável. Pagamento fica paid_manual ou zero_total,
   nunca paid_api. Cada pacote tem uma única retirada.

Reservas Fast, saldo/valor divergente, pacote alterado/retirado e chave Pix alterada
ficam em conflito. Os registros locais e o diário enviado permanecem disponíveis.
Nada é sobrescrito. Há savepoint por operação, índices únicos e bloqueios para
impedir duplicações em reenvios e concorrência. Dependências pendentes impedem
importar pacotes/retiradas relacionados até serem regularizadas.

A conferência manual e o vínculo ao código existente continuam disponíveis para
duplicidades já resolvidas. Registros incorretos podem ser marcados como não
aplicados com motivo e auditoria. Consultar registros enviados recupera o diário
do operador. Aparelhos não se comunicam durante uma queda; evitar atender o mesmo
pacote em dois aparelhos.

## Proteção

IndexedDB com AES-GCM e chave derivada da senha local por PBKDF2/SHA-256, 310 mil
iterações e salt aleatório. Chave/senha e tokens não são persistidos no envelope.
Bloqueio manual ou após 15 minutos sem uso. Abas antigas não sobrescrevem versões
novas. As respostas de API não são guardadas pelo service worker; apenas a
interface genérica e a biblioteca QR ficam em cache no escopo /offline/.

Manter o bloqueio de tela do PC e baixar backup protegido após o atendimento.
Não limpar os dados do navegador antes da sincronização. Armazenamento persistente
é solicitado, mas o navegador pode remover dados. Senha perdida impede recuperar
o backup. Restaurar só no mesmo domínio e sem outra base local no navegador.
Mudança de domínio, banco, operador ou SECRET_KEY exige planejamento de migração.

Limites: preparação até 10 mil clientes/pacotes, envelope local de até 12 MiB,
lotes de até 20 operações e datas de importação automática até oito dias.
Registros mais antigos continuam preservados para conferência. Histórico local
não equivale a uma cópia completa das funções administrativas, públicas ou de
integrações online: essas páginas continuam dependendo do servidor.

## Instalação primeiro em testes

Após integrar em develop:

~~~bash
cd /home/ubuntu/sistema-ponto-de-coleta-adelinha-teste
git pull --ff-only origin develop
sudo systemctl restart ponto-coleta-teste.service
sudo systemctl is-active ponto-coleta-teste.service
~~~

Atualizar dados no PC depois de instalar. O cofre e backups da versão anterior
são preservados; os registros antigos de Conferência manual exigem revisão.
Pix manual em SITE_ENVIRONMENT=test é bloqueado por padrão para não reaproveitar
a chave real por acidente. Configurar uma chave de teste no ambiente e habilitar
STAGING_OFFLINE_PIX_ENABLED=1 somente em /etc/ponto-coleta/site-teste.env,
reiniciando apenas esse serviço. Isso não cria homologação bancária.

As colunas de observação/proveniência e índices são criados na inicialização.
Não precisa de instância Oracle ou banco adicionais. A produção só receberá a
alteração após validação em testes e autorização para promover/instalar.
