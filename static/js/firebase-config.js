// static/js/firebase-config.js
//
// ⚠️ ESTE ARQUIVO PRECISA SER PREENCHIDO COM AS SUAS CHAVES DO FIREBASE
// antes das notificações push funcionarem. Veja o README.md, seção
// "Notificações push", pra saber onde pegar cada valor.
//
// Enquanto os valores abaixo estiverem com "SUBSTITUA_AQUI", o botão
// "Ativar notificações" vai aparecer no painel mas não vai funcionar —
// isso é esperado até você configurar o Firebase.

const firebaseConfig = {
    apiKey: "AIzaSyB9kPFR2HOURs2GTIPBAzh2yxR7Ey-QrwI",
    authDomain: "myu-store.firebaseapp.com",
    projectId: "myu-store",
    storageBucket: "myu-store.firebasestorage.app",
    messagingSenderId: "1426836254",
    appId: "1:1426836254:web:9380c2b18ef4c79a2a570f",
};

// VAPID key (Web Push certificate) — pegue em:
// Firebase Console > Configurações do Projeto > Cloud Messaging > Web Push certificates
const VAPID_KEY = "BPSk1F-JOLcwNOKi-KzhX7rrBYd32I8Px3BYmzp7sXctYBUpYNsyxjtaAQ6-PVMZkw6qaL9bMgSfvZ33T8LAzEc";

firebase.initializeApp(firebaseConfig);
const messaging = firebase.messaging();

async function ativarNotificacoes() {
    if (firebaseConfig.apiKey === "SUBSTITUA_AQUI") {
        alert(
            "Notificações push ainda não foram configuradas neste site.\n\n" +
            "Veja o README.md (seção 'Notificações push') para configurar o Firebase."
        );
        return;
    }

    try {
        const permissao = await Notification.requestPermission();
        if (permissao !== "granted") {
            alert("Você precisa permitir notificações para receber avisos de novos pedidos.");
            return;
        }

        const token = await messaging.getToken({ vapidKey: VAPID_KEY });

        await fetch("/push/registrar", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token }),
        });

        alert("Notificações ativadas! Você vai receber um aviso a cada novo pedido.");
    } catch (err) {
        console.error("Erro ao ativar notificações:", err);
        alert("Não foi possível ativar as notificações. Veja o console para detalhes.");
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("ativarNotificacoesBtn");
    if (btn) {
        btn.addEventListener("click", ativarNotificacoes);
    }
});

// Recebe notificação enquanto o painel está aberto em primeiro plano
messaging.onMessage((payload) => {
    console.log("Notificação recebida em primeiro plano:", payload);
    if (payload.notification) {
        alert(`${payload.notification.title}\n${payload.notification.body}`);
    }
});
