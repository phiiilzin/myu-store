# MYU Store — Backend Flask

Loja fã-feita de *Grow a Garden*, com painel de vendedor, stock de pets/seeds/gears,
carrinho de compras e sistema de trades entre jogadores.

Esta pasta junta **seus arquivos originais** (HTML/CSS que você já tinha feito) com o
**backend Flask** que faltava — tudo já organizado na estrutura que o Flask espera.

## O que veio de cada lado

| Vinha de você | Eu criei |
|---|---|
| Todos os `.html` e `.css` (visual, layout) | `app.py` (todas as rotas) |
| `database.db` com a tabela `vendedores` | `db/schema.sql`, `db/queries.py`, `db/migrate.py` |
| | `templates/trades.html` + `static/css/trades.css` (não existia) |

Seus HTMLs foram mantidos com o mesmo visual — só troquei trechos fixos por
`{{ variáveis }}` e `{% for %}` do Jinja2 (o motor de template do Flask), pra
eles passarem a mostrar dados reais do banco em vez de texto fixo.

## Estrutura

```
myu-store/
├── app.py                  # ponto de entrada — todas as rotas Flask
├── requirements.txt
├── db/
│   ├── schema.sql            # define as tabelas (vendedores, pets, seeds, gears, trades...)
│   ├── queries.py             # conexão com o SQLite
│   ├── migrate.py              # roda o schema + criptografa senhas antigas + dados de exemplo
│   └── database.db              # seu banco original, já migrado
├── templates/                # HTMLs (Jinja2) — servidos pelo Flask
│   ├── Index.html
│   ├── login.html
│   ├── Painel_ADM.html
│   ├── criar_vendedor.html
│   ├── GEARS_STOCK.html
│   ├── SEEDS_STOCK.html
│   ├── PETS_STOCK.html
│   ├── Carrinho.html
│   └── trades.html            # novo, não existia
└── static/
    ├── css/                   # todos os seus CSS, sem alteração de estilo
    └── assets/                 # ⚠️ vazio — você precisa colocar suas imagens aqui (veja LEIA-ME.txt)
```

## Setup

```bash
cd myu-store
pip install -r requirements.txt
python db/migrate.py     # garante que o schema está atualizado (idempotente, pode rodar sempre)
python app.py
```

Acesse `http://localhost:5000`.

⚠️ **Defina a variável `SECRET_KEY`** antes de rodar em produção, ou toda vez que reiniciar
o servidor todo mundo será deslogado:

```bash
export SECRET_KEY="uma-string-bem-longa-e-aleatoria"
python app.py
```

## Login de vendedor existente

Seu vendedor `phiiilzin` já existia no banco com senha `1234` em texto puro. A migração
**converteu automaticamente** essa senha para hash (`werkzeug.security`) — você continua
logando com `phiiilzin` / `1234`, só que agora a senha real fica protegida no banco.

## Fluxo de uso

1. Vendedor loga em `/login` → vai pro painel em `/painel`
2. No painel, cada seção (Seeds/Gears/Pets) tem um formulário: se o **nome do item já
   existir**, atualiza stock/preço/imagem; se não existir, **cria um item novo**
3. Qualquer vendedor logado pode criar outro vendedor em `/criar_vendedor` (igual ao
   `criar_vendedor.html` que você já tinha, só liguei a lógica)
4. O stock público (`/pets`, `/seeds`, `/gears`) puxa os dados reais do banco e mostra
   um botão "Comprar" que joga o item no carrinho
5. O carrinho (`/carrinho`) soma os itens por sessão de visitante (cookie, sem precisar
   de login) e debita o stock quando a compra é finalizada
6. **Trades** (`/trades`): como não existe cadastro de "jogador" (só vendedor loga),
   a identificação é pelo **nome digitado** — o jogador entra com seu nome no jogo,
   propõe trades pra outro nome, e quem recebe usa esse mesmo nome pra ver e
   responder a proposta

## Decisões importantes

- **Senha de vendedor com hash** (`werkzeug.security.generate_password_hash`), não mais
  texto puro. O `migrate.py` já converteu a que existia.
- **Sessão Flask assinada** (`session['usuario']`) pro login — é o jeito padrão do Flask,
  equivalente ao `session['usuario']` que já aparecia no seu `Painel_ADM.html` original.
- **Carrinho por cookie de sessão, sem exigir login**: cada visitante recebe um ID
  aleatório guardado no cookie; os itens dele ficam vinculados a esse ID no banco.
- **Trades por nome digitado, sem login de jogador**: como o projeto não tinha (e você
  não pediu) um sistema de cadastro pra jogadores comuns, a forma mais simples de
  identificar "de quem é a proposta" é pelo nome que a pessoa digita. É simples de usar,
  mas tem uma limitação: **qualquer um pode digitar qualquer nome** e ver/responder
  propostas endereçadas a esse nome. Se isso for um problema (por exemplo, alguém usar
  o nome de outro jogador pra aceitar uma trade no lugar dele), a próxima melhoria seria
  adicionar uma senha/PIN simples por nome de jogador.
- **3 tabelas separadas** (`pets`, `seeds`, `gears`) em vez de uma só com coluna
  categoria — foi a opção que você escolheu, e bate com a estrutura que seus HTMLs
  já tinham (uma página por categoria).

## Chat por pedido + Notificações push

Quando o cliente finaliza uma compra (`/carrinho/finalizar`):

1. O pedido é criado normalmente (debita stock, salva itens)
2. Uma **sala de chat** é criada automaticamente, vinculada a esse pedido
3. O cliente é **redirecionado direto pro chat** (`/chat/<pedido_id>`)
4. Uma **notificação push** é disparada para todos os vendedores com token
   registrado (se o Firebase estiver configurado — veja abaixo)

O chat é em grupo: todos os vendedores que abrirem aquele pedido caem na
mesma sala, junto com o cliente daquele pedido específico. As mensagens
ficam salvas no banco (tabela `chat_mensagens`) — sair e voltar mantém o
histórico. A atualização em tempo real usa **polling** (o navegador consulta
`/chat/<id>/mensagens` a cada 3 segundos) — simples e suficiente para o
volume de uma loja pequena/média; pode evoluir para WebSocket depois se
o tráfego crescer muito.

**Controle de acesso do chat:**
- O cliente só acessa o chat do **próprio pedido** (verificado pelo cookie de
  sessão que gerou aquele pedido)
- Qualquer vendedor logado acessa **qualquer** chat (visão completa da loja)

### Notificações push (Firebase) — ⚠️ só funciona com HTTPS público

Push notification é uma funcionalidade do **navegador**, não do Flask — e
navegadores só permitem registrar notificações em sites com HTTPS e domínio
público (ou em `localhost` puro, mas não em IPs locais tipo
`127.0.0.1`/Termux). Por isso, **enquanto este projeto rodar local no Termux,
o botão "Ativar notificações" vai aparecer mas não vai funcionar de
verdade** — isso é uma limitação do navegador, não um bug.

Quando você hospedar o site (Render, PythonAnywhere, etc., com HTTPS), siga
estes passos:

1. Vá em [console.firebase.google.com](https://console.firebase.google.com) e
   crie um projeto novo (gratuito)
2. No menu lateral, ative **Cloud Messaging**
3. Em **Configurações do Projeto → Contas de serviço**, clique em
   "Gerar nova chave privada" — isso baixa um arquivo `.json`. Renomeie esse
   arquivo para `firebase-service-account.json` e coloque em `db/`
4. Em **Configurações do Projeto → Cloud Messaging**, role até
   "Web Push certificates" e gere uma chave VAPID
5. Em **Configurações do Projeto → Geral**, role até "Seus apps", crie um
   app Web, e copie os valores de configuração (`apiKey`, `authDomain`, etc.)
6. Preencha esses valores em **dois arquivos** (são os mesmos valores nos dois):
   - `static/js/firebase-config.js` (inclua também a VAPID key)
   - `static/firebase-messaging-sw.js`
7. Instale a dependência:
   ```bash
   pip install firebase-admin
   ```
8. Reinicie o servidor

Depois disso, cada vendedor que logar e clicar em "🔔 Ativar notificações"
no painel vai começar a receber um aviso no celular/navegador a cada novo
pedido finalizado.

Se você pular esses passos, **nada quebra** — o `push.py` detecta que o
Firebase não está configurado e simplesmente não envia nada, sem gerar erro.

## Bot de atendimento (palavras-chave, sem custo)

Enquanto **nenhum vendedor** tiver respondido ainda em um chat de pedido, um
bot simples responde automaticamente as perguntas do cliente. Esse bot **não
usa IA externa** — ele procura por palavras-chave na mensagem do cliente
(ex: "preço", "entrega", "trade") e responde com um texto pré-definido para
aquela palavra-chave. Se nenhuma palavra-chave bater, ele manda uma resposta
padrão genérica. Não tem custo, não precisa de chave de API, não precisa de
cartão de crédito nem conta externa nenhuma.

Assim que **qualquer vendedor** mandar a primeira mensagem naquele chat, o
bot **para de responder ali pra sempre** (mesmo que o vendedor não escreva
de novo depois) — o controle fica na coluna `vendedor_respondeu` da tabela
`chats`.

No chat, mensagens do bot aparecem com um visual diferente (roxo, ícone 🤖)
pra deixar claro que não é um vendedor humano respondendo.

### Editando as regras pelo Painel Admin

Tudo é editável direto pelo painel, na seção "🤖 Bot de Atendimento", sem
precisar tocar em código:

- **Adicionar regra**: define uma nova palavra-chave + resposta
- **Editar regra**: muda o texto de uma regra já existente
- **Remover regra**: apaga uma regra
- **Resposta padrão**: o texto usado quando nenhuma palavra-chave bate

A comparação ignora acento e maiúscula/minúscula — uma regra com a
palavra-chave "preco" também é encontrada se o cliente escrever "PREÇO".

Regras padrão que já vêm configuradas: preço, entrega, como comprar,
horário, trade e pagamento. Edite ou substitua como quiser.

## Stock unificado, Sobre Nós editável e Avaliações

- **`/stock`**: junta Pets, Seeds e Gears em uma página só, com abas. Não
  está mais no menu principal (foi substituída por "Dúvidas"), mas a rota
  continua funcionando — o botão "COMPRAR AGORA" na home aponta pra ela.
  As rotas antigas (`/pets`, `/seeds`, `/gears`) também continuam funcionando.
- **`/sobre-nos`**: texto editável pelo Painel Admin (seção "📝 Editar Sobre
  Nós"), guardado na tabela `configuracoes`. Sempre que precisar mudar o
  texto, é só editar e salvar — não precisa tocar em código.
- **`/avaliacoes`**: lista pública de avaliações (nota 1-5 estrelas +
  comentário). Só quem **finalizou um pedido** pode avaliar, e o formulário
  aparece dentro do próprio chat daquele pedido (`/chat/<id>`) — cada pedido
  só pode ser avaliado uma vez.

## Dúvidas (FAQ editável)

- **`/duvidas`**: substituiu "Stock" no menu principal. Mostra um texto
  livre de perguntas e respostas, editável pelo Painel Admin (mesma lógica
  de "Sobre Nós" — guardado em `configuracoes`, chave `duvidas_texto`).

## Suporte (chat com o bot, sem precisar de pedido)

- **`/suporte`**: ligado ao item "Suporte" do menu principal. Abre um chat
  geral com o bot de palavras-chave — não precisa ter comprado nada nem
  estar logado. Cada visitante recebe uma conversa própria (vinculada ao
  cookie de sessão, igual ao carrinho).
- O bot responde normalmente usando as mesmas regras configuradas na seção
  "🤖 Bot de Atendimento" do painel (preço, entrega, trade, etc).
- **Vendedores podem ver e responder** essas conversas pelo Painel Admin,
  no botão "🆘 Suporte" do cabeçalho → lista de conversas (`/suporte/conversas`)
  → abrir uma conversa específica (`/suporte/admin/<id>`).
- Mesma regra do chat de pedido: assim que **um vendedor** escrever na
  conversa, o bot **para de responder ali pra sempre**.

## Ofertas do Dia

A página inicial não mostra mais os 3 cards separados de Pets/Seeds/Gears —
agora tem um único card de **"🔥 Ofertas do Dia"** (o card de Trades
continua). Pelo Painel Admin, na seção "🔥 Ofertas do Dia", o vendedor:

1. Escolhe a categoria (Pets, Seeds ou Gears)
2. Escolhe o item já existente naquela categoria
3. Define um **preço promocional**

O preço original do item (na tabela `pets`/`seeds`/`gears`) **não é
alterado** — a oferta é só um preço alternativo, guardado na tabela
`ofertas_do_dia`, exibido na home com o preço original riscado ao lado do
promocional. Não expira automaticamente: fica assim até o vendedor remover
ou trocar manualmente. Se o item da oferta for excluído do stock, a oferta
correspondente é removida automaticamente (evita ficar com oferta "órfã").

## Emoji nos itens

Cada item de Pets/Seeds/Gears agora tem um campo opcional de **emoji**, ao
lado do campo de imagem, editável pelo Painel Admin. Se o vendedor preencher
os dois (emoji e imagem), **o emoji tem prioridade** — é o que aparece nos
cards do site (stock, home, ofertas do dia). Se só a imagem for preenchida,
a imagem aparece normalmente, como já funcionava antes.

## Rotas principais

| Rota | Método | O que faz |
|---|---|---|
| `/` | GET | Home |
| `/pets`, `/seeds`, `/gears` | GET | Stock público de cada categoria |
| `/login` | GET/POST | Tela e processamento de login |
| `/logout` | GET | Encerra a sessão |
| `/painel` | GET | Painel admin (login obrigatório) |
| `/update_pet`, `/update_seed`, `/update_gear` | POST | Cria ou atualiza item (login obrigatório) |
| `/delete_item/<tabela>/<id>` | POST | Remove item (login obrigatório) |
| `/criar_vendedor` | GET/POST | Cria novo vendedor (login obrigatório) |
| `/carrinho` | GET | Mostra o carrinho da sessão atual |
| `/carrinho/adicionar` | POST | Adiciona item ao carrinho |
| `/carrinho/remover/<id>` | POST | Remove item do carrinho |
| `/carrinho/finalizar` | POST | Fecha o pedido e debita o stock |
| `/trades` | GET | Lista trades recebidas/enviadas (`?nome=`) |
| `/trades/criar` | POST | Propõe uma nova trade |
| `/trades/<id>/aceitar` `/recusar` `/cancelar` | POST | Responde a uma trade |
| `/chat/<pedido_id>` | GET | Abre a sala de chat daquele pedido |
| `/chat/<pedido_id>/mensagens` | GET | JSON com mensagens (usado pelo polling) |
| `/chat/<pedido_id>/enviar` | POST | Envia uma mensagem no chat |
| `/push/registrar` | POST | Salva o token de push do vendedor logado |
| `/stock` | GET | Stock unificado (Pets + Seeds + Gears com abas) |
| `/sobre-nos` | GET | Página pública "Sobre Nós" |
| `/update_sobre_nos` | POST | Atualiza o texto de "Sobre Nós" (login obrigatório) |
| `/avaliacoes` | GET | Lista pública de avaliações |
| `/chat/<pedido_id>/avaliar` | POST | Avalia um pedido (só o dono do pedido) |
| `/bot/regras` | POST | Cria uma nova regra do bot (login obrigatório) |
| `/bot/regras/<id>` | POST | Edita uma regra do bot (login obrigatório) |
| `/bot/regras/<id>/excluir` | POST | Remove uma regra do bot (login obrigatório) |
| `/bot/resposta-padrao` | POST | Atualiza a resposta padrão do bot (login obrigatório) |
| `/duvidas` | GET | Página pública de Dúvidas (FAQ) |
| `/update_duvidas` | POST | Atualiza o texto de Dúvidas (login obrigatório) |
| `/ofertas` | POST | Cria/atualiza uma oferta do dia (login obrigatório) |
| `/ofertas/<id>/excluir` | POST | Remove uma oferta do dia (login obrigatório) |
| `/suporte` | GET | Chat de suporte do visitante (cria a conversa automaticamente) |
| `/suporte/<id>/mensagens` | GET | JSON com mensagens (polling) |
| `/suporte/<id>/enviar` | POST | Envia mensagem na conversa de suporte |
| `/suporte/conversas` | GET | Lista de conversas (login obrigatório) |
| `/suporte/admin/<id>` | GET | Abre uma conversa específica para o vendedor responder |

## ⚠️ Sobre as imagens

Seus HTMLs referenciam imagens (`logo.png`, `fundo.png`, ícones de pets/seeds/gears)
que **não foram enviadas** junto com o restante. Criei a pasta `static/assets/` com um
`LEIA-ME.txt` explicando quais arquivos faltam — o site funciona sem elas (só os `<img>`
aparecem vazios/quebrados até você adicionar os arquivos reais lá).

## Testado

Como o ambiente onde isso foi gerado não tem acesso à internet (não rodei `pip install`
de verdade), usei o Flask que já vinha disponível no ambiente e testei o fluxo completo
com o test client interno do Flask (equivalente a fazer requisições HTTP reais, mas sem
precisar de rede): login certo/errado, painel protegido, criar/editar/remover item,
criar vendedor, adicionar ao carrinho com débito de estoque real, propor trade, e
aceitar trade. Tudo passou. Ainda assim, rode local e me avise se achar algo estranho.
