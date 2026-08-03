# Monitor de Diário Oficial (MS e Campo Grande)

Baixa automaticamente, todo dia, a edição mais recente do:
- **DOE-MS** — Diário Oficial do Estado de Mato Grosso do Sul
- **DIOGRANDE** — Diário Oficial de Campo Grande

Procura pelas palavras-chave definidas em `keywords.json` e, se encontrar algo,
manda um alerta no seu Telegram com o trecho e o link do PDF.

## Passo a passo para colocar no ar

### 1. Criar um bot no Telegram (2 minutos)
1. No Telegram, procure por **@BotFather** e inicie uma conversa.
2. Envie `/newbot`, escolha um nome e um username (precisa terminar em "bot").
3. O BotFather vai te dar um **token** (algo como `123456789:AAH...`). Guarde-o.
4. Envie qualquer mensagem para o seu bot recém-criado (ex: "oi").
5. Acesse no navegador, trocando `SEU_TOKEN`:
   `https://api.telegram.org/botSEU_TOKEN/getUpdates`
6. Procure o campo `"chat":{"id":  NUMERO }` na resposta — esse número é o seu `chat_id`.

### 2. Criar o repositório no GitHub
1. Crie um repositório novo (pode ser privado) no GitHub.
2. Suba todos os arquivos desta pasta para ele (`monitor.py`, `keywords.json`,
   `requirements.txt`, `README.md`, e a pasta `.github/workflows/monitor.yml`).

Se nunca fez isso, o caminho mais simples é pelo próprio site do GitHub:
"Add file" → "Upload files" → arraste os arquivos → Commit.

### 3. Configurar os "Secrets" (dados sensíveis)
No repositório: **Settings → Secrets and variables → Actions → New repository secret**
- `TELEGRAM_BOT_TOKEN` = o token do passo 1
- `TELEGRAM_CHAT_ID` = o chat_id do passo 1

### 4. Ativar e testar
1. Vá na aba **Actions** do repositório.
2. Clique no workflow "Monitor Diário Oficial".
3. Clique em **Run workflow** para testar manualmente (não precisa esperar o cron).
4. Se tudo estiver certo, você recebe uma mensagem no Telegram (ou vê nos logs
   que rodou sem encontrar nada, se nenhuma palavra-chave bateu no dia).

Depois disso ele roda sozinho, de segunda a sexta, às 09h (horário de MS).

## Ajustando

- **Palavras-chave**: edite `keywords.json` livremente — são só listas de texto.
  A busca não diferencia maiúsculas/minúsculas.
- **Horário**: edite a linha `cron` em `.github/workflows/monitor.yml`.
  O horário do cron é sempre em UTC. MS está em UTC-4 o ano todo (sem horário
  de verão atualmente), então "12:00 UTC" = "09:00 em MS".
- **Fins de semana**: o cron acima (`1-5`) já pula sábado e domingo, já que os
  diários normalmente não publicam nesses dias.

## Limitações a saber

- O DOE-MS e o DIOGRANDE mudam o layout do site de vez em quando. Se o script
  parar de encontrar edições, o mais provável é que a estrutura HTML da página
  mudou — nesse caso as funções `get_latest_doems_edition()` e
  `get_latest_diogrande_edition()` em `monitor.py` precisam de um ajuste pontual.
- O site do DIOGRANDE tem restrições de acesso automatizado no `robots.txt`.
  Uma consulta pontual e diária como esta tende a ser tranquila (é conteúdo
  público, uso pessoal, baixo volume), mas vale ter isso em mente.
- PDFs escaneados como imagem (sem texto selecionável) não são lidos — isso é
  raro nesses diários, que normalmente são gerados digitalmente.
