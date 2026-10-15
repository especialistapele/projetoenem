"""
Serviço local de descoberta/download do ENEM.
A descoberta automática usa fontes oficiais do INEP. O lote 2025 possui
URLs diretas conhecidas; para anos anteriores, o sistema aponta o catálogo
oficial do repositório RIEP para evitar adivinhar URLs.
"""
from __future__ import annotations
import hashlib, json, re, html, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

INEP_DOWNLOAD = "https://download.inep.gov.br/enem/provas_e_gabaritos"
RIEP_COLLECTION = "https://riep.inep.gov.br/collections/22b39e5c-3238-4414-9faf-7db037247175"
ALLOWED_PDF_HOSTS = {"download.inep.gov.br", "www.gov.br", "riep.inep.gov.br"}
MAX_PDF_BYTES = 80 * 1024 * 1024

COLORS = {1:"Azul",2:"Amarelo",3:"Branco",4:"Rosa",5:"Cinza"}

def candidate_2025():
    items = []
    # Official regular cadernos for 2025: D1 identifies day 1; D6 identifies day 2.
    books_by_day = (
        (1, "D1", {1: "Azul", 2: "Amarelo", 3: "Branco", 4: "Verde"}),
        (2, "D6", {5: "Amarelo", 6: "Cinza", 7: "Azul", 8: "Verde"}),
    )
    for day, day_code, books in books_by_day:
        for cd, color in books.items():
            for kind, prefix in (("caderno", "PV"), ("gabarito", "GB")):
                url = f"{INEP_DOWNLOAD}/2025_{prefix}_impresso_{day_code}_CD{cd}.pdf"
                items.append({
                    "year": 2025, "application": "regular", "day": day,
                    "color": color, "caderno": cd, "document_type": kind,
                    "filename": Path(url).name, "source_url": url,
                    "official": True, "status": "candidate"
                })
    return items

def check_url(url, timeout=8):
    try:
        req=Request(url, method="HEAD", headers={"User-Agent":"ENEM-Predict/1.0"})
        with urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 400
    except Exception:
        # Some servers reject HEAD; a tiny ranged GET is the fallback.
        try:
            req=Request(url, headers={"User-Agent":"ENEM-Predict/1.0","Range":"bytes=0-1023"})
            with urlopen(req, timeout=timeout) as r:
                return 200 <= r.status < 400
        except Exception:
            return False

def discover_year_page(year:int, application:str="regular"):
    """Lê a página oficial do Inep e extrai links PDF publicados pelo próprio órgão."""
    page=f"https://www.gov.br/inep/pt-br/areas-de-atuacao/avaliacao-e-exames-educacionais/enem/provas-e-gabaritos/{year}"
    try:
        req=Request(page,headers={"User-Agent":"ENEM-Predict/1.0"})
        with urlopen(req,timeout=15) as r: raw=r.read().decode("utf-8","ignore")
    except Exception:
        return []
    out=[]
    for href,title in re.findall(r'href=["\']([^"\']+\.pdf[^"\']*)["\'][^>]*>(.*?)</a>',raw,re.I|re.S):
        url=html.unescape(href)
        if url.startswith('/'): url='https://www.gov.br'+url
        if not url.startswith('http'): continue
        label=re.sub(r'<[^>]+>',' ',html.unescape(title)).strip()
        low=(url+' '+label).lower()
        if application not in low and application not in ('regular',):
            continue
        kind='gabarito' if 'gabarito' in low else ('redacao' if 'red' in low else 'caderno')
        day=2 if any(x in low for x in ('dia 2','d2','dia_2')) else (1 if any(x in low for x in ('dia 1','d1','dia_1')) else None)
        color=next((c for c in COLORS.values() if c.lower() in low),None)
        out.append({"year":year,"application":application,"day":day,"color":color,"document_type":kind,"filename":Path(url.split('?')[0]).name,"source_url":url,"official":True,"available":True,"status":"available","label":label})
    # Deduplicate by URL and keep only exam PDFs.
    seen=set(); uniq=[]
    for x in out:
        if x['source_url'] not in seen: seen.add(x['source_url']); uniq.append(x)
    return uniq

def discover(year_start:int, year_end:int, application:str="regular"):
    out=[]
    for year in range(max(1998,year_start), min(2026,year_end)+1):
        page_items=discover_year_page(year,application)
        if page_items:
            out.extend(page_items)
        else:
            out.append({"year":year,"application":application,"day":None,"color":None,"document_type":"catalog","filename":None,"source_url":RIEP_COLLECTION,"official":True,"available":True,"status":"catalog","message":"A página oficial não respondeu no ambiente local; selecione o caderno no catálogo oficial RIEP."})
    return out

def safe_name(value):
    return re.sub(r"[^A-Za-z0-9._-]+","_", value)

def classify_document(filename: str, label: str = "") -> tuple[str, bool]:
    """Classifica o PDF e informa se é uma versão especial que não deve virar prova."""
    low = (filename + " " + label).lower()
    special = any(token in low for token in ("_ledor", "-ledor", "ampliada", "superampliada"))
    if re.search(r"(^|[_\- ])gb([_\-.]|$)|gabarito", low):
        return "gabarito", special
    if re.search(r"(^|[_\- ])pv([_\-.]|$)|prova|caderno", low):
        return "caderno", special
    return "outro", special

def file_identity(item: dict) -> str:
    """Chave estável da aplicação/caderno, independente da cor ou nome amigável."""
    fn = str(item.get("filename") or item.get("source_url") or "").lower()
    year = item.get("year") or ""
    day = item.get("day") or (int(m.group(1)) if (m := re.search(r"(?:dia|d)(\d)", fn)) else "")
    cd = re.search(r"cd(\d+)", fn)
    code = cd.group(1) if cd else (str(item.get("color") or "sem_codigo").lower())
    kind, special = classify_document(fn, str(item.get("label") or ""))
    return f"{year}|{item.get('application','regular')}|D{day}|CD{code}|{kind}|special={int(special)}"

def validate_pdf_bytes(data: bytes) -> tuple[bool, str]:
    if not data.startswith(b"%PDF"):
        return False, "O conteúdo baixado não é um PDF válido."
    if len(data) < 10240:
        return False, "PDF muito pequeno; download possivelmente incompleto."
    return True, "PDF válido"

def _open_url_with_retries(request, timeout=90, attempts=3):
    """Retry transient network resets/timeouts without retrying HTTP error responses."""
    last_error = None
    for attempt in range(attempts):
        try:
            return urlopen(request, timeout=timeout)
        except HTTPError:
            raise
        except (URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (2 ** attempt))
    raise last_error


def download_pdf(item:dict, base_dir:Path):
    if not item.get("source_url") or item.get("document_type")=="catalog":
        raise ValueError("Item não possui URL direta de PDF.")
    year=str(item["year"])
    color=safe_name(str(item.get("color") or "sem_cor")).lower()
    day=str(item.get("day") or "nao_informado")
    folder=base_dir / year / f"dia_{day}" / color
    folder.mkdir(parents=True, exist_ok=True)
    filename=safe_name(item.get("filename") or Path(item["source_url"]).name)
    dest=folder/filename
    kind, special = classify_document(filename, str(item.get("label") or ""))
    if kind == "outro":
        raise ValueError("Arquivo não identificado como prova (PV) ou gabarito (GB).")
    source_url=str(item["source_url"])
    parsed=urlparse(source_url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_PDF_HOSTS:
        raise ValueError("A origem do PDF deve ser HTTPS e pertencer a um domínio oficial do INEP/Gov.br/RIEP.")
    req=Request(source_url, headers={"User-Agent":"ENEM-Predict/1.0"})
    raw=bytearray()
    with _open_url_with_retries(req, timeout=90) as response:
        final=urlparse(response.geturl())
        if final.scheme != "https" or (final.hostname or "").lower() not in ALLOWED_PDF_HOSTS:
            raise ValueError("O download foi redirecionado para um domínio não autorizado.")
        content_length=response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_PDF_BYTES:
            raise ValueError("O PDF excede o limite de 80 MB.")
        while True:
            chunk=response.read(1024*1024)
            if not chunk: break
            raw.extend(chunk)
            if len(raw) > MAX_PDF_BYTES:
                raise ValueError("O PDF excede o limite de 80 MB.")
    valid, reason = validate_pdf_bytes(bytes(raw))
    if not valid:
        raise ValueError(reason)
    h=hashlib.sha256(bytes(raw)).hexdigest()
    duplicate = None
    if base_dir.exists():
        for existing in base_dir.rglob("*.pdf"):
            try:
                if hashlib.sha256(existing.read_bytes()).hexdigest() == h:
                    duplicate = existing
                    break
            except OSError:
                pass
    if duplicate is not None:
        record={**item,"status":"duplicate","storage_path":str(duplicate.relative_to(base_dir.parent.parent)),
                "sha256":h,"file_size_bytes":len(raw),"document_type":kind,
                "special_version":special,"identity":file_identity(item),
                "validation":"valid","duplicate_of":str(duplicate.relative_to(base_dir.parent.parent))}
        return record
    dest.write_bytes(bytes(raw))
    record={**item,"status":"downloaded","storage_path":str(dest.relative_to(base_dir.parent.parent)),
            "sha256":h,"file_size_bytes":len(raw),"document_type":kind,
            "special_version":special,"identity":file_identity(item),
            "validation":"valid"}
    return record

def write_manifest(base_dir:Path, records:list[dict]):
    manifest=base_dir/"manifest.json"
    manifest.parent.mkdir(parents=True,exist_ok=True)
    existing=[]
    if manifest.exists():
        try: existing=json.loads(manifest.read_text("utf-8"))
        except Exception: existing=[]
    by_url={x.get("source_url"):x for x in existing}
    by_url.update({x.get("source_url"):x for x in records})
    manifest.write_text(json.dumps(list(by_url.values()),ensure_ascii=False,indent=2),encoding="utf-8")
    return manifest
