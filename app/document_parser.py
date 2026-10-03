import os
import io
from typing import List, Dict, Any, Tuple
import pypdf
import docx
import pptx
import openpyxl


def extract_text_from_pdf(file_bytes: bytes) -> List[Dict[str, Any]]:
    """PDFからページごとのテキストを抽出"""
    pages = []
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    for idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        text = text.strip()
        if text:
            pages.append({"section": f"Page {idx + 1}", "text": text})
    return pages


def extract_text_from_docx(file_bytes: bytes) -> List[Dict[str, Any]]:
    """Word(.docx)からパラグラフおよび表のテキストを抽出"""
    doc = docx.Document(io.BytesIO(file_bytes))
    sections = []
    
    # 段落
    current_para = []
    for p in doc.paragraphs:
        txt = p.text.strip()
        if txt:
            current_para.append(txt)
    if current_para:
        sections.append({"section": "本文", "text": "\n".join(current_para)})

    # 表
    for t_idx, table in enumerate(doc.tables):
        table_rows = []
        for row in table.rows:
            row_data = [cell.text.strip() for cell in row.cells]
            table_rows.append(" | ".join(row_data))
        if table_rows:
            sections.append({"section": f"表 {t_idx + 1}", "text": "\n".join(table_rows)})

    return sections


def extract_text_from_pptx(file_bytes: bytes) -> List[Dict[str, Any]]:
    """PowerPoint(.pptx)からスライドごとのテキストを抽出"""
    prs = pptx.Presentation(io.BytesIO(file_bytes))
    slides = []
    for idx, slide in enumerate(prs.slides):
        slide_texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    t = paragraph.text.strip()
                    if t:
                        slide_texts.append(t)
        if slide_texts:
            slides.append({
                "section": f"Slide {idx + 1}",
                "text": "\n".join(slide_texts)
            })
    return slides


def extract_text_from_xlsx(file_bytes: bytes) -> List[Dict[str, Any]]:
    """Excel(.xlsx)からシートごとのテキストを抽出"""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    sheets = []
    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        rows_text = []
        for row in sheet.iter_rows(values_only=True):
            cleaned = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if cleaned:
                rows_text.append(" | ".join(cleaned))
        if rows_text:
            sheets.append({
                "section": f"Sheet: {sheet_name}",
                "text": "\n".join(rows_text)
            })
    return sheets


def extract_text_from_plain(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """テキストファイル(.txt, .md, .csv)の抽出 (utf-8 / cp932フォールバック)"""
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = file_bytes.decode("cp932")
        except UnicodeDecodeError:
            text = file_bytes.decode("utf-8", errors="ignore")
    return [{"section": filename, "text": text.strip()}]


def extract_document_sections(file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    """拡張子に応じてテキストセクションを抽出"""
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_bytes)
    elif ext == ".docx":
        return extract_text_from_docx(file_bytes)
    elif ext == ".pptx":
        return extract_text_from_pptx(file_bytes)
    elif ext in [".xlsx", ".xls"]:
        return extract_text_from_xlsx(file_bytes)
    elif ext in [".txt", ".md", ".csv", ".json"]:
        return extract_text_from_plain(file_bytes, filename)
    else:
        raise ValueError(f"未対応のファイル形式です: {ext} (対応形式: PDF, DOCX, PPTX, XLSX, TXT, MD, CSV)")


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """テキストを指定サイズでオーバーラップさせながら分割"""
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        if end >= len(text):
            break
        start += (chunk_size - overlap)
    return chunks


def parse_and_chunk_file(file_bytes: bytes, filename: str, chunk_size: int = 500, overlap: int = 50) -> List[Dict[str, Any]]:
    """ファイルをパースしてRAG検索用のチャンク一覧を生成"""
    sections = extract_document_sections(file_bytes, filename)
    all_chunks = []
    
    for sec in sections:
        section_name = sec["section"]
        raw_text = sec["text"]
        text_chunks = chunk_text(raw_text, chunk_size=chunk_size, overlap=overlap)
        
        for idx, ch in enumerate(text_chunks):
            all_chunks.append({
                "content": ch,
                "metadata": {
                    "source": filename,
                    "section": section_name,
                    "chunk_index": idx,
                    "total_chunks_in_section": len(text_chunks)
                }
            })
    return all_chunks
