import json
import re
import requests
import typer
import csv
import os
from datetime import datetime
from typing import Optional

app = typer.Typer()

API_KEY = "8fb88b4abede1240132fd7c0d6b700c0"

BASE_URL = "https://api.itjobs.pt"


def api_get(path: str, params: dict | None = None):
    if params is None:
        params = {}

    if not API_KEY or API_KEY == "AQUI_A_TUA_API_KEY":
        raise RuntimeError("API_KEY não definida")

    params["api_key"] = API_KEY
    url = f"{BASE_URL}{path}"

    headers = {
        # User-Agent real retirado de um exemplo funcional
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/50.0.2661.102 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


def parse_date_flexible(s: str) -> Optional[datetime]:
    """Tenta várias formas de parse de data. Retorna datetime ou None."""
    if not s:
        return None
    s = s.strip()
    iso_match = re.search(r"\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}:\d{2})?", s)
    if iso_match:
        piece = iso_match.group(0)
        try:
            return datetime.fromisoformat(piece.replace("Z", "+00:00"))
        except Exception:
            pass
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    m = re.search(r"(\d{4})[^\d]?(\d{2})[^\d]?(\d{2})", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            pass
    return None


def extract_job_date(job: dict) -> Optional[datetime]:
    """Tenta extrair a data de publicação de um job a partir de várias chaves comuns."""
    keys = [
        "published", "published_at", "publication_date", "posted", "posted_at",
        "date", "created", "created_at", "publish_date", "date_posted"
    ]
    for k in keys:
        v = job.get(k)
        if isinstance(v, str):
            d = parse_date_flexible(v)
            if d:
                return d
        if isinstance(v, (int, float)):
            try:
                return datetime.fromtimestamp(int(v))
            except Exception:
                pass
    text = " ".join(filter(None, [job.get("title", ""), job.get("body", "")]))
    d = parse_date_flexible(text)
    return d


def extract_company_name(job: dict) -> str:
    comp = job.get("company") or {}
    if isinstance(comp, dict):
        return comp.get("name", "") or ""
    if isinstance(comp, str):
        return comp
    return ""


def extract_salary(job: dict) -> str:
    for k in ("salary", "salary_description", "salary_text", "remuneration", "salary_min", "salary_max"):
        if k in job and job[k]:
            return str(job[k])
    if isinstance(job.get("contract"), dict):
        return str(job["contract"].get("salary", "")) or ""
    return ""


def extract_locations(job: dict) -> str:
    locs = job.get("locations", [])
    if isinstance(locs, list):
        names = []
        for l in locs:
            if isinstance(l, dict):
                names.append(l.get("name", ""))
            else:
                names.append(str(l))
        return ", ".join([n for n in names if n])
    return str(locs or "")


def jobs_to_csv(jobs: list, path: str):
    fields = ["titulo", "empresa", "descricao", "data_publicacao", "salario", "localizacao"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for job in jobs:
            dt = extract_job_date(job)
            writer.writerow({
                "titulo": job.get("title", ""),
                "empresa": extract_company_name(job),
                "descricao": job.get("body", "") or job.get("description", "") or "",
                "data_publicacao": dt.isoformat() if dt else "",
                "salario": extract_salary(job),
                "localizacao": extract_locations(job),
            })


@app.command("top")
def top(n: int, csv: bool = typer.Option(False, "--csv", help="Exportar resultado para CSV"),
        csv_path: str = typer.Option("", "--csv-path", help="Caminho do ficheiro CSV (opcional)")):
    """
    Listar os N trabalhos mais recentes publicados pela itjobs.pt.
    """
    dados = api_get("/job/list.json", {"limit": n})
    resultados = dados.get("results", dados)
    if isinstance(resultados, dict):
        resultados = resultados.get("results", []) or []
    print(json.dumps(resultados, ensure_ascii=False, indent=2))

    if csv:
        path = csv_path or f"top_{n}.csv"
        jobs_to_csv(resultados, path)
        typer.echo(f"CSV guardado em: {path}")


@app.command("search")
def search(localidade: str, empresa: str, n: int,
           csv: bool = typer.Option(False, "--csv", help="Exportar resultado para CSV"),
           csv_path: str = typer.Option("", "--csv-path", help="Caminho do ficheiro CSV (opcional)")):
    """
    Listar N trabalhos do tipo part-time, publicados por empresa e localidade.
    """
    dados = api_get("/job/search.json", {"q": localidade, "limit": 100})
    todos = dados.get("results", [])

    loc = localidade.lower()
    emp = empresa.lower()

    filtrados = []

    for job in todos:
        tipos = {str(t["id"]) for t in job.get("types", [])} if job.get("types") else set()
        if "2" not in tipos:
            continue

        company = extract_company_name(job).lower()
        locais = " ".join(l.get("name", "").lower() for l in job.get("locations", [])) if job.get("locations") else ""

        if emp in company and loc in locais:
            filtrados.append(job)
            if len(filtrados) >= n:
                break

    print(json.dumps(filtrados, ensure_ascii=False, indent=2))

    if csv:
        path = csv_path or f"search_{empresa}_{localidade}.csv".replace(" ", "_")
        jobs_to_csv(filtrados, path)
        typer.echo(f"CSV guardado em: {path}")


@app.command("type")
def job_type(job_id: int):
    dados = api_get("/job/get.json", {"id": job_id})

    texto = ""

    if dados.get("title"):
        texto += dados["title"].lower() + " "
    if dados.get("body"):
        texto += dados["body"].lower() + " "

    texto += json.dumps(dados.get("contract", "")).lower()
    texto += json.dumps(dados.get("types", "")).lower()
    texto += json.dumps(dados.get("locations", "")).lower()

    if "remote" in texto or "remoto" in texto:
        print("remote")
    elif "híbr" in texto or "hibr" in texto:
        print("hybrid")
    elif "presencial" in texto or "on-site" in texto:
        print("onsite")
    else:
        print("other")


@app.command("skills")
def skills(data_inicial: str, data_final: str):
    """
    Contar ocorrências de skills nas descrições dos anúncios entre duas datas.
    Formato das datas: YYYY-MM-DD (ou outros formatos comuns).
    """
    di = parse_date_flexible(data_inicial)
    df = parse_date_flexible(data_final)
    if not di or not df:
        typer.echo("Não foi possível interpretar as datas. Usa por exemplo YYYY-MM-DD.")
        raise typer.Exit(code=1)
    if df < di:
        typer.echo("dataFinal é anterior a dataInicial.")
        raise typer.Exit(code=1)

    skills_list = [
        "python", "r", "sql", "docker", "aws", "git", "tensorflow", "pandas", "numpy",
        "javascript", "java", "c#", "c\\+\\+", "scala", "spark", "react", "node"
    ]
    counts = {s: 0 for s in skills_list}

    page = 0
    limit = 100
    while True:
        dados = api_get("/job/search.json", {"limit": limit, "offset": page * limit})
        todos = dados.get("results", [])
        if not todos:
            break
        for job in todos:
            dt = extract_job_date(job)
            if not dt:
                continue
            if not (di <= dt <= df):
                continue
            text = " ".join(filter(None, [job.get("title", ""), job.get("body", ""), extract_company_name(job)]))
            text = text.lower()
            for s in skills_list:
                pattern = r"\b" + s + r"\b"
                matches = re.findall(pattern, text, flags=re.IGNORECASE)
                counts[s] += len(matches)
        if len(todos) < limit:
            break
        page += 1
        if page >= 20:
            break

    result = sorted([{"skill": k.replace("\\", ""), "count": v} for k, v in counts.items()], key=lambda x: x["count"], reverse=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
