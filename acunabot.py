# ============================================================
#  AcunaBot — WhatsApp Cloud API
#  Python + Flask — Desplegar en Railway (gratis)
#  Autor: Nestor Acuña Q. — nestoracuna1968@gmail.com
# ============================================================
#
#  Variables de entorno necesarias (.env o Railway Dashboard):
#
#   VERIFY_TOKEN      → El token que le pones en Meta Developer Portal al
#                       configurar el webhook. Pon: acunabot2026secreta
#   WHATSAPP_TOKEN    → "Token de acceso temporal" en Meta > tu app >
#                       WhatsApp > Configuración de API
#   PHONE_NUMBER_ID   → "ID del número de teléfono" en el mismo lugar
#   NESTOR_WA_NUMBER  → Tu número WhatsApp con código de país, sin +
#                       Ej: 573043045809
#   PORT              → Railway lo pone automáticamente (no tocar)
# ============================================================

import os
import time
import threading
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ── Credenciales ────────────────────────────────────────────
VERIFY_TOKEN    = os.getenv("VERIFY_TOKEN",    "acunabot2026secreta")
WHATSAPP_TOKEN  = os.getenv("WHATSAPP_TOKEN",  "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
NESTOR_WA       = os.getenv("NESTOR_WA_NUMBER","")   # ej: 573043045809
PORT            = int(os.getenv("PORT", 5000))

API_URL = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"

# ── Estado de conversaciones en memoria ─────────────────────
# Diccionario: numero → {"paso": str, "datos": dict, "ts": float}
_estados: dict = {}
_lock = threading.Lock()
CACHE_TTL = 600  # 10 minutos

def get_estado(numero: str) -> dict:
    with _lock:
        data = _estados.get(numero)
        if data and time.time() - data["ts"] < CACHE_TTL:
            return {"paso": data["paso"], "datos": dict(data["datos"])}
    return {"paso": "inicio", "datos": {}}

def set_estado(numero: str, estado: dict):
    with _lock:
        _estados[numero] = {
            "paso":  estado["paso"],
            "datos": dict(estado.get("datos", {})),
            "ts":    time.time()
        }

def reset_estado(numero: str):
    with _lock:
        _estados.pop(numero, None)

# ── Webhook GET — verificación Meta ─────────────────────────
@app.route("/webhook", methods=["GET"])
def verify():
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Webhook verificado por Meta")
        return challenge, 200
    return "Token incorrecto", 403

# ── Webhook POST — mensajes entrantes ───────────────────────
@app.route("/webhook", methods=["POST"])
def recibir():
    try:
        body    = request.get_json(silent=True) or {}
        entry   = (body.get("entry") or [{}])[0]
        change  = (entry.get("changes") or [{}])[0]
        value   = change.get("value", {})
        message = (value.get("messages") or [None])[0]

        if not message:
            return "OK", 200

        from_num = message.get("from", "")
        tipo     = message.get("type", "")

        if tipo == "text":
            texto = message["text"]["body"].lower().strip()
            manejar_texto(from_num, texto)

        elif tipo == "interactive":
            inter = message.get("interactive", {})
            if inter.get("type") == "button_reply":
                manejar_boton(from_num, inter["button_reply"]["id"])
            elif inter.get("type") == "list_reply":
                manejar_boton(from_num, inter["list_reply"]["id"])

    except Exception as err:
        print(f"❌ Error en /webhook POST: {err}")

    return "OK", 200

# ── Lógica principal ─────────────────────────────────────────
TRIGGERS_MENU = {
    "hola","buenos","buenas","info","información","informacion",
    "ayuda","help","menu","menú","inicio","start",
    "1","2","3","4","acunabot"
}

def manejar_texto(from_num: str, texto: str):
    estado = get_estado(from_num)

    # Flujo: esperando nombre de empresa
    if estado["paso"] == "esperando_empresa":
        estado["datos"]["empresa"] = texto.upper()
        estado["paso"] = "esperando_nit"
        set_estado(from_num, estado)
        enviar_texto(from_num,
            f"🔢 ¿Cuál es el NIT de *{estado['datos']['empresa']}*?\n\n"
            "(Sin dígito de verificación, solo el número)"
        )
        return

    # Flujo: esperando NIT
    if estado["paso"] == "esperando_nit":
        estado["datos"]["nit"] = texto
        estado["paso"] = "esperando_software"
        set_estado(from_num, estado)
        enviar_botones(from_num,
            f"💻 ¿Qué software contable usa {estado['datos']['empresa']}?",
            [
                {"id": "sw_siigo", "titulo": "SIIGO Nube"},
                {"id": "sw_wo",    "titulo": "World Office"},
                {"id": "sw_otro",  "titulo": "Otro software"},
            ]
        )
        return

    # Flujo: esperando NIT de soporte
    if estado["paso"] == "esperando_nit_soporte":
        nit = texto
        reset_estado(from_num)
        enviar_texto(from_num,
            "✅ Recibido. *Néstor Acuña* le contacta en breve.\n\n"
            "Mientras tanto puede escribirnos directamente al:\n"
            "📱 *3043045809*"
        )
        notificar_nestor(
            f"🔧 SOPORTE SOLICITADO\nNIT: {nit}\nWhatsApp: {from_num}"
        )
        return

    # Cualquier otro texto → menú principal
    enviar_menu_principal(from_num)


def manejar_boton(from_num: str, btn_id: str):
    estado = get_estado(from_num)

    # ── Menú principal ──────────────────────────────────────
    if btn_id == "btn_prueba":
        estado = {"paso": "esperando_empresa", "datos": {}}
        set_estado(from_num, estado)
        enviar_texto(from_num,
            "¡Perfecto! 🎉 Vamos a activar su prueba gratis de 2 días.\n\n"
            "📋 ¿Cuál es el nombre o razón social de su empresa?"
        )
        return

    if btn_id == "btn_precios":
        enviar_precios(from_num)
        return

    if btn_id == "btn_soporte":
        estado = {"paso": "esperando_nit_soporte", "datos": {}}
        set_estado(from_num, estado)
        enviar_texto(from_num,
            "🔧 *Soporte AcunaBot*\n\n"
            "Para atenderle rápido:\n\n"
            "🔢 ¿Cuál es el NIT de su empresa?"
        )
        return

    # ── Flujo prueba: selección de software ────────────────
    if btn_id in ("sw_siigo", "sw_wo", "sw_otro") and estado["paso"] == "esperando_software":
        sw = {"sw_siigo": "SIIGO Nube", "sw_wo": "World Office", "sw_otro": "Otro software"}[btn_id]
        empresa = estado["datos"].get("empresa", "")
        nit     = estado["datos"].get("nit", "")
        reset_estado(from_num)

        enviar_texto(from_num,
            "✅ *¡Solicitud recibida!*\n\n"
            f"🏢 Empresa: *{empresa}*\n"
            f"🔢 NIT: *{nit}*\n"
            f"💻 Software: *{sw}*\n\n"
            "Le enviamos el instalador y lo acompañamos en la configuración. ¡Gracias! 🚀"
        )
        notificar_nestor(
            f"🆕 LEAD PRUEBA GRATIS\n"
            f"Empresa: {empresa}\nNIT: {nit}\nSoftware: {sw}\nWhatsApp: {from_num}"
        )
        return

    # ── Flujo precios: cantidad de empresas ────────────────
    if btn_id == "p_1":
        enviar_cierre_precios(from_num, "1 empresa", "$250.000/mes")
        return
    if btn_id == "p_2_3":
        enviar_cierre_precios(from_num, "2 a 3 empresas", "$400.000 – $550.000/mes")
        return
    if btn_id == "p_mas":
        enviar_cierre_precios(from_num, "4 o más empresas", "$800.000 – $1.100.000/mes")
        return

    # ── Cierre precios ──────────────────────────────────────
    if btn_id == "cta_prueba":
        estado = {"paso": "esperando_empresa", "datos": {}}
        set_estado(from_num, estado)
        enviar_texto(from_num,
            "📋 ¿Cuál es el nombre o razón social de su empresa?"
        )
        return

    if btn_id == "cta_nestor":
        reset_estado(from_num)
        enviar_texto(from_num,
            "📞 Le conectamos con *Néstor Acuña* directamente.\n\n"
            "Escriba su pregunta o comentario y él le responde personalmente. 🙏"
        )
        notificar_nestor(
            f"📞 CLIENTE QUIERE HABLAR DIRECTO\nWhatsApp: {from_num}"
        )
        return

    # Si no reconoció el botón → menú
    enviar_menu_principal(from_num)


# ── Mensajes predefinidos ────────────────────────────────────
def enviar_menu_principal(from_num: str):
    reset_estado(from_num)
    enviar_botones(from_num,
        "👋 Bienvenido a *AcunaBot* 🤖\n\n"
        "Software colombiano para descargar, contabilizar y acusar "
        "facturas electrónicas DIAN automáticamente.\n"
        "Compatible con *SIIGO Nube* y *World Office*.\n\n"
        "¿En qué le puedo ayudar?",
        [
            {"id": "btn_prueba",  "titulo": "🆓 Prueba gratis 2 días"},
            {"id": "btn_precios", "titulo": "💰 Ver precios"},
            {"id": "btn_soporte", "titulo": "🔧 Soporte técnico"},
        ]
    )

def enviar_precios(from_num: str):
    enviar_botones(from_num,
        "💰 *Planes AL DÍA — Todo incluido*\n\n"
        "▸ Prueba gratis → 2 días\n"
        "▸ 1 empresa      → *$250.000/mes*\n"
        "▸ 2 empresas     → *$400.000/mes*\n"
        "▸ 3 empresas     → *$550.000/mes*\n"
        "▸ 4–7 empresas   → *$800.000/mes*\n"
        "▸ 8–12 empresas  → *$1.100.000/mes*\n\n"
        "✅ Todas las funciones incluidas\n"
        "✅ Sin contratos de permanencia\n\n"
        "¿Cuántas empresas maneja actualmente?",
        [
            {"id": "p_1",   "titulo": "1 empresa"},
            {"id": "p_2_3", "titulo": "2 a 3 empresas"},
            {"id": "p_mas", "titulo": "4 o más"},
        ]
    )

def enviar_cierre_precios(from_num: str, plan: str, precio: str):
    enviar_botones(from_num,
        f"Su plan ideal: *{plan}* a *{precio}*\n\n"
        "¿Arrancamos con la prueba gratis?",
        [
            {"id": "cta_prueba",  "titulo": "✅ Sí, prueba gratis"},
            {"id": "cta_nestor",  "titulo": "📞 Hablar con Néstor"},
        ]
    )


# ── Funciones de envío (WhatsApp Cloud API) ──────────────────
def enviar_texto(to: str, texto: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": texto}
    }
    _llamar_api(payload)

def enviar_botones(to: str, cuerpo: str, botones: list):
    """WhatsApp permite máximo 3 botones, título máx 20 chars."""
    btns_wa = [
        {
            "type": "reply",
            "reply": {
                "id":    b["id"],
                "title": b["titulo"][:20]
            }
        }
        for b in botones[:3]
    ]
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": cuerpo},
            "action": {"buttons": btns_wa}
        }
    }
    _llamar_api(payload)

def _llamar_api(payload: dict):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("⚠️  WHATSAPP_TOKEN o PHONE_NUMBER_ID no configurados")
        return
    try:
        resp = requests.post(
            API_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                "Content-Type":  "application/json"
            },
            timeout=10
        )
        if resp.status_code != 200:
            print(f"⚠️  API resp {resp.status_code}: {resp.text}")
        else:
            print(f"✅ Mensaje enviado a {payload.get('to','?')}")
    except Exception as e:
        print(f"❌ Error llamando API: {e}")


# ── Notificación a Néstor ────────────────────────────────────
def notificar_nestor(mensaje: str):
    """Envía WhatsApp directo a Néstor con la notificación."""
    if not NESTOR_WA:
        print(f"📬 NOTIF NESTOR (sin número configurado): {mensaje}")
        return
    enviar_texto(NESTOR_WA, f"📬 *AcunaBot — Notificación*\n\n{mensaje}")


# ── Health check ─────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "AcunaBot corriendo ✅", "bot": "AcunaBot"}), 200


# ── Arranque ──────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"🤖 AcunaBot arrancando en puerto {PORT}...")
    app.run(host="0.0.0.0", port=PORT, debug=False)
