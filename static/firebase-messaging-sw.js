// static/firebase-messaging-sw.js
//
// Service Worker necessário para o Firebase Cloud Messaging entregar
// notificações mesmo quando o navegador/aba está em segundo plano ou fechado.
//
// ⚠️ Este arquivo precisa ficar na RAIZ do site (não dentro de /static/css
// ou similar) para o navegador conseguir registrá-lo corretamente como
// Service Worker do domínio inteiro. O app.py já expõe uma rota especial
// /firebase-messaging-sw.js que serve este arquivo na raiz.
//
// Preencha os mesmos valores que você usou em static/js/firebase-config.js

importScripts("https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js");

firebase.initializeApp({
    apiKey: "AIzaSyB9kPFR2HOURs2GTIPBAzh2yxR7Ey-QrwI",
    authDomain: "myu-store.firebaseapp.com",
    projectId: "myu-store",
    storageBucket: "myu-store.firebasestorage.app",
    messagingSenderId: "1426836254",
    appId: "1:1426836254:web:9380c2b18ef4c79a2a570f",
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
    const title = payload.notification?.title || "MYU Store";
    const options = {
        body: payload.notification?.body || "",
        icon: "/static/assets/logo.png",
    };
    self.registration.showNotification(title, options);
});
