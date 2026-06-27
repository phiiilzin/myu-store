-- ============================================
-- MYU STORE - Schema do banco de dados (SQLite)
-- ============================================

-- Tabela já existente no projeto original. Mantemos o nome/colunas
-- ("usuario", "senha") para não quebrar o que já estava feito,
-- mas a partir de agora "senha" guarda um HASH, nunca texto puro.
CREATE TABLE IF NOT EXISTS vendedores (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL UNIQUE,
    senha   TEXT NOT NULL
);

-- Itens de PETS
CREATE TABLE IF NOT EXISTS pets (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nome    TEXT NOT NULL,
    stock   INTEGER NOT NULL DEFAULT 0,
    preco   REAL NOT NULL DEFAULT 0,
    imagem  TEXT,
    emoji   TEXT
);

-- Itens de SEEDS
CREATE TABLE IF NOT EXISTS seeds (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nome    TEXT NOT NULL,
    stock   INTEGER NOT NULL DEFAULT 0,
    preco   REAL NOT NULL DEFAULT 0,
    imagem  TEXT,
    emoji   TEXT
);

-- Itens de GEARS
CREATE TABLE IF NOT EXISTS gears (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nome    TEXT NOT NULL,
    stock   INTEGER NOT NULL DEFAULT 0,
    preco   REAL NOT NULL DEFAULT 0,
    imagem  TEXT,
    emoji   TEXT
);

-- Carrinho: cada linha é "1 item de uma categoria, dentro do carrinho de uma sessão"
-- session_id é um identificador aleatório guardado no cookie de sessão do Flask
CREATE TABLE IF NOT EXISTS carrinho_itens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    categoria   TEXT NOT NULL CHECK (categoria IN ('pets', 'seeds', 'gears')),
    item_id     INTEGER NOT NULL,
    quantidade  INTEGER NOT NULL DEFAULT 1,
    criado_em   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Pedidos finalizados (quando o carrinho é "fechado" no checkout)
CREATE TABLE IF NOT EXISTS pedidos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    total       REAL NOT NULL,
    criado_em   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pedido_itens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id   INTEGER NOT NULL,
    categoria   TEXT NOT NULL,
    nome        TEXT NOT NULL,
    preco       REAL NOT NULL,
    quantidade  INTEGER NOT NULL,
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE
);

-- Trades: jogador A oferece itens pra jogador B, que aceita ou recusa.
-- Como não há cadastro de "jogador" separado (só vendedores fazem login),
-- trades são identificadas por um nome de jogador (texto livre) + um código
-- único de trade, que cada lado usa para consultar o status.
CREATE TABLE IF NOT EXISTS trades (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo         TEXT NOT NULL UNIQUE,
    nome_ofertante TEXT NOT NULL,
    nome_receptor  TEXT NOT NULL,
    mensagem       TEXT,
    status         TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'aceita', 'recusada', 'cancelada')),
    criado_em      TEXT NOT NULL DEFAULT (datetime('now')),
    resolvido_em   TEXT
);

CREATE TABLE IF NOT EXISTS trade_itens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id    INTEGER NOT NULL,
    lado        TEXT NOT NULL CHECK (lado IN ('oferta', 'pedido')),
    nome_item   TEXT NOT NULL,
    quantidade  INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_carrinho_session ON carrinho_itens(session_id);
CREATE INDEX IF NOT EXISTS idx_trade_itens_trade ON trade_itens(trade_id);
CREATE INDEX IF NOT EXISTS idx_trades_codigo ON trades(codigo);

-- ============================================
-- CHAT POR PEDIDO + NOTIFICAÇÕES PUSH
-- ============================================

-- Token de notificação push (Firebase Cloud Messaging) de cada vendedor.
-- Um vendedor pode logar em mais de um dispositivo/navegador, então cada
-- token é uma linha separada. Quando o navegador gera um token novo pro
-- mesmo vendedor, substituímos pelo mais recente (ver UNIQUE em "token").
CREATE TABLE IF NOT EXISTS vendedor_push_tokens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    vendedor_id INTEGER NOT NULL,
    token       TEXT NOT NULL UNIQUE,
    criado_em   TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (vendedor_id) REFERENCES vendedores(id) ON DELETE CASCADE
);

-- Uma sala de chat por pedido finalizado. Todos os vendedores caem na
-- mesma sala (chat em grupo com o cliente daquele pedido).
-- "vendedor_respondeu" controla se algum vendedor humano já escreveu nessa
-- sala — usado para decidir se o bot de IA ainda deve responder ou não.
CREATE TABLE IF NOT EXISTS chats (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id           INTEGER NOT NULL UNIQUE,
    vendedor_respondeu  INTEGER NOT NULL DEFAULT 0,
    criado_em           TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE
);

-- Mensagens dentro de uma sala. "autor_tipo" diferencia se quem mandou foi
-- o cliente (sem login), um vendedor logado, ou o bot de IA respondendo
-- automaticamente enquanto nenhum vendedor chegou ainda.
CREATE TABLE IF NOT EXISTS chat_mensagens (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id       INTEGER NOT NULL,
    autor_tipo    TEXT NOT NULL CHECK (autor_tipo IN ('cliente', 'vendedor', 'bot')),
    autor_nome    TEXT NOT NULL,
    mensagem      TEXT NOT NULL,
    criado_em     TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_mensagens_chat ON chat_mensagens(chat_id);
CREATE INDEX IF NOT EXISTS idx_vendedor_push_vendedor ON vendedor_push_tokens(vendedor_id);

-- ============================================
-- AVALIAÇÕES + CONFIGURAÇÕES EDITÁVEIS (Sobre Nós)
-- ============================================

-- Avaliação da loja, vinculada a um pedido específico (só quem comprou pode
-- avaliar). UNIQUE em pedido_id garante uma avaliação por pedido, evitando
-- que a mesma pessoa avalie o mesmo pedido várias vezes.
CREATE TABLE IF NOT EXISTS avaliacoes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id   INTEGER NOT NULL UNIQUE,
    nota        INTEGER NOT NULL CHECK (nota BETWEEN 1 AND 5),
    comentario  TEXT,
    criado_em   TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE
);

-- Tabela de configurações simples chave/valor — usada hoje para o texto
-- editável da página "Sobre Nós", mas serve para qualquer outro texto
-- editável que apareça no futuro sem precisar de tabela nova.
CREATE TABLE IF NOT EXISTS configuracoes (
    chave   TEXT PRIMARY KEY,
    valor   TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_avaliacoes_pedido ON avaliacoes(pedido_id);

-- ============================================
-- BOT DE ATENDIMENTO (palavras-chave, editável pelo Painel Admin)
-- ============================================

-- Cada regra: se a mensagem do cliente contiver "palavra_chave" (sem
-- diferenciar acento/maiúscula), o bot responde com "resposta".
-- "ordem" define a prioridade — regras com ordem menor são checadas primeiro.
CREATE TABLE IF NOT EXISTS bot_respostas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    palavra_chave TEXT NOT NULL,
    resposta      TEXT NOT NULL,
    ordem         INTEGER NOT NULL DEFAULT 0,
    criado_em     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bot_respostas_ordem ON bot_respostas(ordem);

-- ============================================
-- OFERTAS DO DIA
-- ============================================

-- Cada linha vincula um item já existente (de pets/seeds/gears) como uma
-- "oferta do dia", com um preço promocional. O preço original do item
-- (na tabela pets/seeds/gears) não é alterado — a oferta é só um preço
-- alternativo exibido na home, editável/removível pelo vendedor quando quiser.
CREATE TABLE IF NOT EXISTS ofertas_do_dia (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria       TEXT NOT NULL CHECK (categoria IN ('pets', 'seeds', 'gears')),
    item_id         INTEGER NOT NULL,
    preco_promocional REAL NOT NULL,
    ordem           INTEGER NOT NULL DEFAULT 0,
    criado_em       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (categoria, item_id)
);

CREATE INDEX IF NOT EXISTS idx_ofertas_ordem ON ofertas_do_dia(ordem);

-- ============================================
-- SUPORTE (chat geral, sem pedido associado)
-- ============================================

-- Uma conversa de suporte por sessão de visitante (igual ao carrinho, usa
-- o cookie de sessão pra identificar quem é quem, sem precisar de login).
-- "vendedor_respondeu" funciona igual ao chat de pedido: assim que um
-- vendedor escreve, o bot para de responder naquela conversa específica.
CREATE TABLE IF NOT EXISTS suporte_conversas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT NOT NULL UNIQUE,
    vendedor_respondeu  INTEGER NOT NULL DEFAULT 0,
    criado_em           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS suporte_mensagens (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    conversa_id   INTEGER NOT NULL,
    autor_tipo    TEXT NOT NULL CHECK (autor_tipo IN ('cliente', 'vendedor', 'bot')),
    autor_nome    TEXT NOT NULL,
    mensagem      TEXT NOT NULL,
    criado_em     TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (conversa_id) REFERENCES suporte_conversas(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_suporte_mensagens_conversa ON suporte_mensagens(conversa_id);
CREATE INDEX IF NOT EXISTS idx_suporte_conversas_session ON suporte_conversas(session_id);
