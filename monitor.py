"""
Monitor de Diário Oficial - MS (Estadual) e Campo Grande (DIOGRANDE)

O que este script faz, todo dia:
1. Encontra a edição mais recente do Diário Oficial de MS (DOE-MS), baixa,
   extrai o texto e procura pelas palavras-chave em keywords.json.
2. Para o DIOGRANDE (Campo Grande), como o site bloqueia acesso automático:
   - Manda uma mensagem no Telegram com o link da página de edições, pedindo
     pro usuário baixar o PDF do dia e mandar de volta pelo chat.
   - Verifica se o usuário mandou algum PDF novo no chat do bot; se sim,
     extrai o texto, procura as palavras-chave e responde com o resultado.
3. Se encontrar alguma palavra-chave, envia um alerta pro Telegram com o
   trecho e o link (ou nome do arquivo).
4. Guarda em state.json o que já foi processado, pra não repetir aviso.

Variáveis de ambiente necessárias (configuradas como "Secrets" no GitHub):
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from bs4 import BeautifulSoup

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

STATE_FILE = "state.json"
KEYWORDS_FILE = "keywords.json"

DOE_MS_URL = "https://www.diariooficial.ms.gov.br/"
DIOGRANDE_EDICOES_URL = "https://diogrande.campogrande.ms.gov.br/edicoes/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


# ---------- utilidades ----------

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("AVISO: TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não configurados. "
              "Mensagem não enviada:\n", message)
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for i in range(0, len(message), 4000):
        chunk = message[i:i + 4000]
        resp = requests.post(url, data={
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        }, timeout=30)
        if resp.status_code != 200:
            print("Erro ao enviar Telegram:", resp.status_code, resp.text)


def download_pdf(url, dest):
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    with open(dest, "wb") as f:
        f.write(r.content)
    return dest


def extract_text(pdf_path):
    if pdfplumber is None:
        raise RuntimeError("pdfplumber não instalado")
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts)


def find_matches(text, keywords):
    """Retorna lista de (palavra-chave, trecho) para cada ocorrência encontrada."""
    matches = []
    lower_text = text.lower()
    for kw in keywords:
        kw_lower = kw.lower()
        start = 0
        while True:
            idx = lower_text.find(kw_lower, start)
            if idx == -1:
                break
            snippet_start = max(0, idx - 120)
            snippet_end = min(len(text), idx + len(kw) + 120)
            snippet = text[snippet_start:snippet_end].replace("\n", " ").strip()
            matches.append((kw, snippet))
            start = idx + len(kw_lower)
            if sum(1 for m in matches if m[0] == kw) >= 3:
                break
    return matches


# ---------- DOE-MS (estadual) ----------

def get_latest_doems_edition():
    r = requests.get(DOE_MS_URL, headers=HEADERS, timeout=60)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf") and "diario" in href.lower():
            label = a.get_text(strip=True) or href
            return {"label": label, "url": href}
    return None


# ---------- DIOGRANDE (municipal) - fluxo manual via Telegram ----------

def get_telegram_updates(offset):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return [], offset
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"timeout": 5}
    if offset:
        params["offset"] = offset
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    updates = data.get("result", [])
    new_offset = offset
    if updates:
        new_offset = updates[-1]["update_id"] + 1
    return updates, new_offset


def download_telegram_file(file_id, dest):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/getFile"
    resp = requests.get(url, params={"file_id": file_id}, timeout=30)
    resp.raise_for_status()
    file_path = resp.json()["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    r = requests.get(file_url, timeout=60)
    r.raise_for_status()
    with open(dest, "wb") as f:
        f.write(r.content)
    return dest


def process_diogrande_manual(state, keywords, alerts):
    # 1) Avisa uma vez por dia pedindo pro usuário mandar o PDF
    today_key = f"diogrande_link_sent:{datetime.utcnow().date().isoformat()}"
    if not state.get(today_key):
        alerts.append(
            "📎 *DIOGRANDE* - não consigo acessar automaticamente (o site bloqueia robôs).\n"
            f"Acesse {DIOGRANDE_EDICOES_URL}, baixe o PDF da edição de hoje e "
            "me mande esse arquivo aqui mesmo no Telegram que eu verifico pra você."
        )
        state[today_key] = True

    # 2) Verifica se o usuário já mandou algum PDF novo no chat
    offset = state.get("telegram_offset")
    try:
        updates, new_offset = get_telegram_updates(offset)
    except Exception as e:
        print("Erro ao verificar mensagens do Telegram:", e)
        return

    for update in updates:
        message = update.get("message", {})
        document = message.get("document")
        if not document:
            continue
        file_name = document.get("file_name", "arquivo.pdf")
        if not file_name.lower().endswith(".pdf"):
            continue

        print(f"[DIOGRANDE] Arquivo recebido do usuário: {file_name}")
        pdf_path = "/tmp/diogrande_manual.pdf"
        try:
            download_telegram_file(document["file_id"], pdf_path)
            text = extract_text(pdf_path)
        except Exception as e:
            alerts.append(f"⚠️ Não consegui processar o arquivo {file_name}: {e}")
            continue

        matches = find_matches(text, keywords)
        if matches:
            lines = [f"📌 *DIOGRANDE (manual)* - {file_name}", ""]
            for kw, snippet in matches:
                lines.append(f"🔎 _{kw}_: ...{snippet}...")
            alerts.append("\n".join(lines))
        else:
            alerts.append(
                f"✅ *DIOGRANDE (manual)* - {file_name}: nenhuma palavra-chave encontrada."
            )

    state["telegram_offset"] = new_offset


# ---------- fluxo principal ----------

def process_source(name, edition, state, keywords, alerts):
    if not edition:
        print(f"[{name}] Não foi possível localizar a edição mais recente.")
        return

    key = f"{name}:{edition['url']}"
    if state.get(key):
        print(f"[{name}] Edição já verificada: {edition['label']}")
        return

    print(f"[{name}] Nova edição encontrada: {edition['label']} -> {edition['url']}")
    pdf_path = f"/tmp/{name.replace(' ', '_')}.pdf"
    try:
        download_pdf(edition["url"], pdf_path)
        text = extract_text(pdf_path)
    except Exception as e:
        print(f"[{name}] Erro ao baixar/ler PDF: {e}")
        return

    matches = find_matches(text, keywords)
    if matches:
        lines = [f"📌 *{name}* - {edition['label']}", edition["url"], ""]
        for kw, snippet in matches:
            lines.append(f"🔎 _{kw}_: ...{snippet}...")
        alerts.append("\n".join(lines))
    else:
        print(f"[{name}] Nenhuma palavra-chave encontrada nesta edição.")

    state[key] = datetime.utcnow().isoformat()


def main():
    keywords = load_json(KEYWORDS_FILE, [])
    if not keywords:
        print("AVISO: keywords.json está vazio ou não existe. Nada será buscado.")
    state = load_json(STATE_FILE, {})

    alerts = []

    try:
        doe = get_latest_doems_edition()
    except Exception as e:
        doe = None
        print("Erro ao consultar DOE-MS:", e)
    process_source("DOE-MS", doe, state, keywords, alerts)

    # DIOGRANDE: tenta automático primeiro; se falhar, usa o fluxo manual
    try:
        diogrande = get_latest_diogrande_edition()
    except Exception as e:
        diogrande = None
        print("Erro ao consultar DIOGRANDE automaticamente:", e)

    if diogrande:
        process_source("DIOGRANDE", diogrande, state, keywords, alerts)
    else:
        process_diogrande_manual(state, keywords, alerts)

    # limpa state antigo (mais de 60 dias) pra não crescer pra sempre
    cutoff = datetime.utcnow() - timedelta(days=60)
    state = {
        k: v for k, v in state.items()
        if not isinstance(v, str) or _safe_parse(v) is None or _safe_parse(v) > cutoff
    }
    save_json(STATE_FILE, state)

    if alerts:
        send_telegram("\n\n---\n\n".join(alerts))
    else:
        print("Nenhum alerta a enviar hoje.")


def _safe_parse(value):
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


if __name__ == "__main__":
    main()
