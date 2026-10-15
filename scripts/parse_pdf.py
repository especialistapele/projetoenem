"""Parser ENEM: prova e gabarito em staging, sem gravar diretamente nas questions."""
from __future__ import annotations
import argparse, json, re, unicodedata
from pathlib import Path
import pdfplumber

QUESTION_START_PATTERN = re.compile(r"(?im)^[ \t]*(?:QUEST[ÃA]O|QUESTAO)[ \t]*(?:N[º°.]?[ \t]*)?(\d{1,3})(?=[ \t.:)\-–—]|$)[ \t]*[.:)\-–—]?[ \t]*")
ALT_PATTERN = re.compile(r"(?im)^\s*([A-E])\s*[\)\.]\s+")
ANSWER_ROW_PATTERN = re.compile(r"(?m)^\s*(\d{1,3})\s+([A-E])\s*$")

def normalize_text(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return unicodedata.normalize("NFC", text).strip()

def extract_raw_pages(pdf_path: str) -> list[str]:
    pages=[]
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages.append(normalize_text(page.extract_text() or ""))
    return pages

def split_into_questions(full_text: str) -> list[dict]:
    matches=list(QUESTION_START_PATTERN.finditer(full_text))
    questions=[]
    seen=set()
    for i,m in enumerate(matches):
        number=int(m.group(1))
        if number in seen or number < 1 or number > 200: continue
        seen.add(number)
        end=matches[i+1].start() if i+1 < len(matches) else len(full_text)
        block=normalize_text(full_text[m.end():end])
        alt_matches=list(ALT_PATTERN.finditer(block))
        statement=block
        alternatives=[]
        if alt_matches:
            statement=normalize_text(block[:alt_matches[0].start()])
            for j, am in enumerate(alt_matches):
                end=alt_matches[j+1].start() if j+1 < len(alt_matches) else len(block)
                text=normalize_text(block[am.end():end])
                if text:
                    alternatives.append({"letter":am.group(1).upper(),"text":text})
        questions.append({"number":number,"statement_text":statement,"alternatives":alternatives})
    return sorted(questions,key=lambda x:x["number"])

def parse_answer_key(full_text: str) -> dict[int,str]:
    # Handles the common text extraction of INEP gabarito PDFs.
    answers={}
    for m in ANSWER_ROW_PATTERN.finditer(full_text):
        n=int(m.group(1)); letter=m.group(2).upper()
        if 1 <= n <= 200: answers[n]=letter
    # Fallback for compact rows such as "1 D 2 A 3 C".
    for m in re.finditer(r"\b(\d{1,3})\s*[-:]?\s*([A-E])\b", full_text):
        n=int(m.group(1));
        if 1 <= n <= 200: answers.setdefault(n,m.group(2).upper())
    return answers

def infer_metadata(filename: str, document_text: str = "") -> dict:
    low = filename.lower()
    myear = re.search(r"(?:19|20)\d{2}", low)
    mcd = re.search(r"cd(\d+)", low)
    year = int(myear.group(0)) if myear else None
    caderno = int(mcd.group(1)) if mcd else None
    cover = (document_text or "")[:6000].lower()

    # Em alguns arquivos do INEP, o nome usa D6 para o segundo dia.
    if re.search(r"2\s*[º°o]?\s*dia|segundo dia", cover):
        day = 2
    elif re.search(r"1\s*[º°o]?\s*dia|primeiro dia", cover):
        day = 1
    else:
        mday = re.search(r"(?:dia|d)(\d)", low)
        raw_day = int(mday.group(1)) if mday else None
        day = 2 if raw_day == 6 else (raw_day if raw_day in (1, 2) else None)

    color_names = ("Azul", "Amarelo", "Branco", "Verde", "Cinza", "Rosa", "Laranja", "Roxo")
    color = next((name for name in color_names if re.search(r"\b" + re.escape(name.lower()) + r"\b", low)), None)
    if not color:
    color = next((name for name in color_names if re.search(r"\b" + re.escape(name.lower()) + r"\b", low)), None)

    # Fallback oficial específico da aplicação regular de 2025.
    if not color and year == 2025:
        color_by_booklet = {
            (1, 1): "Azul", (1, 2): "Amarelo", (1, 3): "Branco", (1, 4): "Verde",
            (2, 5): "Amarelo", (2, 6): "Cinza", (2, 7): "Azul", (2, 8): "Verde",
            (1, 9): "Laranja", (1, 10): "Roxo", (2, 11): "Laranja", (2, 12): "Roxo",
        }
        color = color_by_booklet.get((day, caderno))

    special = any(x in low for x in ("ledor", "ampliada", "superampliada"))
    return {"year": year, "day": day, "caderno": caderno, "color": color, "special_version": special}

def expected_count_or_actual(questions: list[dict], expected_count: int | None) -> int:
    return expected_count if expected_count is not None else len(questions)


def parse_pdf(pdf_path: str, kind: str="prova") -> dict:
    pages=extract_raw_pages(pdf_path)
    meta=infer_metadata(Path(pdf_path).name)
    text="\n".join(pages)
    if kind == "gabarito":
        answers=parse_answer_key(text)
        return {"source_file":Path(pdf_path).name,"document_type":"gabarito","pages":len(pages),"answers_found":len(answers),"answers":answers,**meta}
    questions=split_into_questions(text)
    raw_numbers = [int(m.group(1)) for m in QUESTION_START_PATTERN.finditer(text)]
    duplicate_numbers = len(raw_numbers) != len(set(raw_numbers))
    day = meta.get("day")
    expected_count = 90 if day in (1, 2) else None
    expected_start = 1 if day == 1 else (91 if day == 2 else None)
    expected_numbers = set(range(expected_start, expected_start + expected_count)) if expected_start is not None else None
    complete_numbering = (
        expected_count is None
        or (len(questions) == expected_count and {q["number"] for q in questions} == expected_numbers)
    )
    diagnostics={"min_question":min([q["number"] for q in questions],default=None),
                 "max_question":max([q["number"] for q in questions],default=None),
                 "questions_with_5_alternatives":sum(len(q["alternatives"])==5 for q in questions),
                 "duplicate_numbers": duplicate_numbers,
                 "raw_question_headers": len(raw_numbers),
                 "expected_question_count": expected_count,
                 "complete_numbering": complete_numbering}
    diagnostics["quality_status"] = (
        "ready"
        if questions
        and diagnostics["questions_with_5_alternatives"] == expected_count_or_actual(questions, expected_count)
        and not diagnostics["duplicate_numbers"]
        and complete_numbering
        else "review"
    )
    return {"source_file":Path(pdf_path).name,"document_type":"caderno","pages":len(pages),"questions_found":len(questions),"questions":questions,
            "diagnostics":diagnostics,**meta}

def main():
    p=argparse.ArgumentParser(); p.add_argument("pdf_path"); p.add_argument("--kind",choices=["prova","gabarito"],default="prova"); p.add_argument("--year",type=int); p.add_argument("--color",default=None); p.add_argument("--out",default=None); a=p.parse_args()
    result=parse_pdf(a.pdf_path,a.kind); result.update({"year":a.year,"color":a.color})
    out=Path(a.out or f"{Path(a.pdf_path).stem}_parsed.json"); out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"output":str(out),"document_type":result["document_type"],"questions_found":result.get("questions_found"),"answers_found":result.get("answers_found")},ensure_ascii=False))
if __name__ == "__main__": main()
