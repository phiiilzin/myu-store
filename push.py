# push.py
"""
Integração com Firebase Cloud Messaging (FCM) para enviar notificações
push aos vendedores quando um pedido é finalizado.

IMPORTANTE: isso só funciona de verdade quando o site estiver hospedado
com HTTPS e domínio público. Em localhost/Termux, o navegador BLOQUEIA
o registro de push notifications (é uma exigência de segurança do próprio
navegador, não uma limitação deste código).

Como configurar quando for hospedar (resumo, instruções completas no README):
  1. Criar um projeto em https://console.firebase.google.com
  2. Ativar "Cloud Messaging"
  3. Gerar uma "chave de conta de serviço" (Project Settings > Service Accounts
     > Generate new private key) e salvar como db/firebase-service-account.json
  4. Pegar a "Web Push certificate" (VAPID key) em Project Settings > Cloud
     Messaging, e colar no static/js/firebase-config.js
  5. Instalar a dependência: pip install firebase-admin

Enquanto esses passos não forem feitos, as funções aqui simplesmente não
enviam nada e registram um aviso no log — o resto do site continua
funcionando normalmente (o chat funciona sem depender de push).
"""

import os
import json

FIREBASE_CREDENTIALS_PATH = os.path.join(
    os.path.dirname(__file__), "db", "firebase-service-account.json"
)

_firebase_app = None
_firebase_disponivel = False

try:
    import firebase_admin
    from firebase_admin import credentials, messaging

    if os.path.exists(FIREBASE_CREDENTIALS_PATH):
        cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
        _firebase_app = firebase_admin.initialize_app(cred)
        _firebase_disponivel = True
    else:
        print(
            "[push] Arquivo db/firebase-service-account.json não encontrado. "
            "Notificações push estão desativadas até você configurar o Firebase "
            "(veja README.md, seção 'Notificações push')."
        )
except ImportError:
    print(
        "[push] Biblioteca 'firebase-admin' não instalada. "
        "Rode 'pip install firebase-admin' quando for ativar notificações push."
    )


def push_disponivel():
    return _firebase_disponivel


def enviar_notificacao_pedido(tokens, pedido_id, total):
    """
    Envia uma notificação push para uma lista de tokens de dispositivo.
    Se o Firebase não estiver configurado, não faz nada (retorna silenciosamente).

    tokens: lista de strings (tokens FCM dos vendedores)
    pedido_id: id do pedido finalizado
    total: valor total do pedido
    """
    if not _firebase_disponivel or not tokens:
        return {"enviado": False, "motivo": "push não configurado ou sem tokens"}

    from firebase_admin import messaging

    sucesso = 0
    falhas = 0

    for token in tokens:
        try:
            mensagem = messaging.Message(
                notification=messaging.Notification(
                    title="🛒 Novo pedido na MYU Store!",
                    body=f"Pedido #{pedido_id} - Total: R$ {total:.2f}. Toque para abrir o chat.",
                ),
                data={
                    "pedido_id": str(pedido_id),
                    "tipo": "novo_pedido",
                },
                token=token,
            )
            messaging.send(mensagem)
            sucesso += 1
        except Exception as e:
            print(f"[push] Falha ao enviar para token {token[:12]}...: {e}")
            falhas += 1

    return {"enviado": True, "sucesso": sucesso, "falhas": falhas}
