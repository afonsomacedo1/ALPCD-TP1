#Código TP1

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




#Código TP2

import json
import csv
import re
import os
from datetime import datetime
from collections import defaultdict
from typing import Optional, Dict, Any, List, Tuple
import requests
import typer
from bs4 import BeautifulSoup

API_KEY = os.environ.get("ITJOBS_API_KEY", "AQUI_A_TUA_API_KEY")
BASE_URL = "https://api.itjobs.pt"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TeamlyzerScraper/1.0)"}

app = typer.Typer()
get_app = typer.Typer()
statistics_app = typer.Typer()
list_app = typer.Typer()

app.add_typer(get_app, name="get")
app.add_typer(statistics_app, name="statistics")
app.add_typer(list_app, name="list")

def api_get(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if params is None:
        params = {}
    if not API_KEY or API_KEY == "AQUI_A_TUA_API_KEY":
        raise RuntimeError("API key não configurada (ITJOBS_API_KEY).")
    params["api_key"] = API_KEY
    r = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def parse_date_flexible(s: str) -> Optional[datetime]:
    if not s:
        return None
    s = s.strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None


def extract_job_date(job: Dict[str, Any]) -> Optional[datetime]:
    for k in ("published", "created_at", "date"):
        if k in job and isinstance(job[k], str):
            d = parse_date_flexible(job[k])
            if d:
                return d
    return None


def extract_company_name(job: Dict[str, Any]) -> str:
    comp = job.get("company")
    if isinstance(comp, dict):
        return comp.get("name", "") or ""
    if isinstance(comp, str):
        return comp
    return ""


def normalize_text(s: str) -> str:

    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    return s


def slugify_company_name(s: str) -> str:

    s = s.lower().strip()
    s = re.sub(r"[’'`]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s


def safe_get(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return r.text
    except Exception:
        return None
    return None


def find_company_url_in_ranking(company_name: str) -> Optional[str]:
    html = safe_get("https://pt.teamlyzer.com/companies/ranking")
    if not html:
        return None

    target = normalize_text(company_name)
    soup = BeautifulSoup(html, "html.parser")

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        txt = a.get_text(" ", strip=True)
        if "/companies/" in href and txt:
            if target and target in normalize_text(txt):
                if href.startswith("http"):
                    return href
                return "https://pt.teamlyzer.com" + href
    return None


def get_teamlyzer_company_url(company_name: str) -> Optional[str]:

    url = find_company_url_in_ranking(company_name)
    if url:
        return url


    slug = slugify_company_name(company_name)
    if not slug:
        return None

    candidate = f"https://pt.teamlyzer.com/companies/{slug}"
    html = safe_get(candidate)
    if html:
        return candidate

    return None


def scrape_teamlyzer_company(company_url: str) -> Dict[str, Any]:
    html = safe_get(company_url)
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")

    def pick_text(selectors: List[str]) -> str:
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                t = el.get_text(" ", strip=True)
                if t:
                    return t
        return ""

    benefits_url = company_url.rstrip("/") + "/benefits-and-values"
    benefits_html = safe_get(benefits_url)
    benefits_text = ""
    if benefits_html:
        bs = BeautifulSoup(benefits_html, "html.parser")
        items = [x.get_text(" ", strip=True) for x in bs.select(".benefit, .benefits li, .tag")]
        items = [i for i in items if i]
        if items:
            benefits_text = ", ".join(items[:30])

    return {
        "teamlyzer_company_url": company_url,
        "teamlyzer_rating": pick_text([".rating-value", ".rating .value", ".rating"]),
        "teamlyzer_description": pick_text([".company-description", ".description", ".company__description"]),
        "teamlyzer_benefits": benefits_text,
        "teamlyzer_salary": pick_text([".salary-average", ".salary", ".average-salary"]),
    }


def iter_all_itjobs_jobs(limit: int = 100) -> List[Dict[str, Any]]:
    page = 1
    all_jobs: List[Dict[str, Any]] = []
    while True:
        data = api_get("/job/list.json", {"limit": limit, "page": page})
        batch = data.get("results", [])
        if not batch:
            break
        all_jobs.extend(batch)
        page += 1
    return all_jobs


def write_kv_csv(filename: str, obj: Dict[str, Any]) -> None:
    with open(filename, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["key", "value"])
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                w.writerow([k, json.dumps(v, ensure_ascii=False)])
            else:
                w.writerow([k, v])

@get_app.command("jobID")
def get_job(
    job_id: int = typer.Argument(..., help="ID do job no itjobs"),
    csv_out: bool = typer.Option(False, "--csv", help="Exportar CSV"),
):
    job = api_get("/job/get.json", {"id": job_id})

    company = extract_company_name(job)
    if company:
        company_url = get_teamlyzer_company_url(company)
        if company_url:
            job.update(scrape_teamlyzer_company(company_url))

    print(json.dumps(job, ensure_ascii=False, indent=2))

    if csv_out:
        write_kv_csv(f"job_{job_id}.csv", job)

@statistics_app.command("zone")
def statistics_zone(
    limit: int = typer.Option(100, "--limit", help="Tamanho da página na API (não o total)"),
    out: str = typer.Option("statistics.csv", "--out", help="Nome do CSV de saída"),
):
    jobs = iter_all_itjobs_jobs(limit=limit)

    stats: Dict[Tuple[str, str], int] = defaultdict(int)

    for job in jobs:
        zonas = [l.get("name", "") for l in job.get("locations", []) if isinstance(l, dict)]
        tipos = [t.get("name", "") for t in job.get("types", []) if isinstance(t, dict)]

        if not zonas:
            zonas = [""]
        if not tipos:
            tipos = [""]

        for z in zonas:
            z = (z or "").strip()
            for t in tipos:
                t = (t or "").strip()
                stats[(z, t)] += 1

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Zona", "Tipo de Trabalho", "Nº de vagas"])
        for (z, t), c in sorted(stats.items(), key=lambda x: (-x[1], x[0][0], x[0][1])):
            writer.writerow([z, t, c])

    print(out)

@list_app.command("skills")
def list_skills(
    position: str = typer.Argument(..., help='Nome da posição / termo (ex: "data scientist")'),
    csv_out: bool = typer.Option(False, "--csv", help="Exportar CSV"),
    out: str = typer.Option("skills.csv", "--out", help="Nome do CSV de saída (se --csv)"),
):

    tag = position.strip().replace(" ", "%20")

    url = f"https://pt.teamlyzer.com/companies/jobs?tags={tag}&order=most_relevant"
    html = safe_get(url)
    if not html:
        raise RuntimeError("Não foi possível obter a página do Teamlyzer (jobs).")

    soup = BeautifulSoup(html, "html.parser")

    counts: Dict[str, int] = defaultdict(int)

    for el in soup.select(".tag, a.tag, span.tag"):
        s = el.get_text(" ", strip=True).lower()
        s = re.sub(r"\s+", " ", s).strip()
        if s:
            counts[s] += 1

    top10 = sorted(
        [{"skill": k, "count": v} for k, v in counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )[:10]

    print(json.dumps(top10, ensure_ascii=False, indent=2))

    if csv_out:
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["skill", "count"])
            w.writeheader()
            w.writerows(top10)
        print(out)


if __name__ == "__main__":
    app()

