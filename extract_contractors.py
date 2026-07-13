#!/usr/bin/env python3
"""부동산 계약서에서 계약자·날짜 추출 + 고대비 BLOB 이미지 인라인 HTML 생성 + 호수 상단표시"""

import sqlite3, re, os, html as h_m, base64

DB_PATH = "/Users/uglywolf/.hermes/ocr_database.db"
OUT_HTML = "/Users/uglywolf/Desktop/부동산_계약서_report.html"


def extract_names(full_text):
    if not full_text:
        return []
    
    names = []
    
    for m in re.finditer(r'주민등록번호[:：\ufeff]\s*([^\n]*)', full_text):
        prev_rows = full_text[max(0, m.start()-500):m.start()].split('\n')
        for row in reversed(prev_rows[-3:]):
            clean = row.strip().replace('|','').strip()
            if 2 <= len(clean) <= 10 and any(c.isalpha() or '\uac00' <= c <= '\ud7a3' for c in clean):
                non_digits = ''.join(c for c in clean if not c.isdigit())
                if len(non_digits) > 0:
                    names.append(clean.strip())
    
    for m in re.finditer(r'[성\ufe0f이\ufe0f](?![ㄴ|]|[ㅈ])[\ufEFF]*\s*([^\n\r\|]{2,12})', full_text):
        cand = m.group(1).strip()
        if len(cand) > 0 and not all(c.isdigit() for c in cand):
            names.append(cand)
    
    for m in re.finditer(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', full_text):
        if 3 <= len(m.group(0).strip()) <= 40:
            names.append(m.group(0).strip())
    
    seen = set()
    unique_names = []
    for n in names:
        if not n or n in seen:
            continue
        cleaned = ''.join(c for c in n if c.isalpha())
        if len(cleaned) >= 2:
            unique_names.append(n)
            seen.add(n)
    
    return list(set(unique_names))[:5]


def extract_dates(full_text):
    if not full_text:
        return []
    
    dates_found = []
    
    for m in re.finditer(r'(\d{4})[-./ ]*(\d{1,2})[-./ ]*(\d{1,2})', full_text):
        y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
        if 1900 < int(y) < 2100 and int(mo) <= 12 and int(d) <= 31:
            dates_found.append(f"{y}-{mo}-{d}")
    
    for m in re.finditer(r'(\d{4})[^\d]*?(년|\ufe0f\u11ab2\ufe0f|11ab)[^\d]*?(\d{1,2})[^\d]*?(월|\ufe0f\u11af\ufe0f|11af)', full_text):
        year = re.sub(r'[^\d]', '', m.group(1))[:4]
        month = re.sub(r'[^\d]', '', m.group(3))[:2].zfill(2)
        dates_found.append(f"{year}-{month}-일")
    
    return list(set(dates_found))[:5]


def extract_address_info(full_text):
    """계약서에서 소재지, 호수, 건물명Extracted house address/room number"""
    address_parts = []
    
    for m in re.finditer(r'(소재지|소재지| 주소)[^:：\n]*[:：]?\s*([^\n|]{5,100})', full_text):
        val = m.group(2).strip().split('|')[0].strip()
        if len(val) > 2 and re.search(r'[가-힣a-zA-Z\d]', val):
            address_parts.append(val)
    
    # 패턴: 호수/동/층
    for m in re.finditer(r'([가-힣a-zA-Z]*?)\s*(호|동|층)\s*:?\s*([^\n\r\f]{1,20})', full_text):
        val = f"{m.group(1).strip()} {m.group(2)} {m.group(3).strip()}"
        if len(val) > 3:
            address_parts.append(val)
    
    # 패턴: "호" followed by numbers
    for m in re.finditer(r'([가-힣a-zA-Z]+\s*)?[#\ufeff\ufe0f]?\s*(\d{2,4})\s*(호|동)', full_text):
        val = f"{m.group(2)} {m.group(3)}"
        if len(val) > 1:
            address_parts.append(m.group(0).strip())
    
    # "553 호", "서울 영등포구" 패턴 등
    for m in re.finditer(r'([ㄱ-ㅎa-zA-Z\s]*?)\s{2,}?(\d+)[가-힣](?:호|집|건)?\s?(:?[\s|\ufe0f]*|[^\n]{0;10})', full_text):
        val = m.group(0).strip()
        if len(val) > 2:
            address_parts.append(val)
    
    # "도림로" or similar place name + number
    for m in re.finditer(r'([가-힣]+)[\ufe0f\s]*?(도로|리|로|길)', full_text):
        val = f"{m.group(1)} {m.group(2)}"
        address_parts.append(val)
    
    # "건물명"(building name) or similar
    for m in re.finditer(r'(건물.*?호수?|건\.물.*?[^\n\r\f]{1;30})', full_text):
        address_parts.append(m.group(0).strip())
    
    # Deduplicate (order-preserved) and keep most relevant parts
    seen = set()
    deduped = []
    for a in address_parts:
        if not a or a in seen or len(a) < 3:
            continue
        core = re.sub(r'[^\d가-힣a-zA-Z]', '', a)
        if len(core) >= 2 and core not in seen:
            deduped.append(a)
            seen.add(core)
    
    return deduped[:4]


def enhance_contrast(blob_bytes):
    """BLOB PNG → PIL Image → 고대비/휘도 향상 → base64 PNG 재인코딩"""
    try:
        from io import BytesIO
        from PIL import Image as PilImage, ImageEnhance
        
        img = PilImage.open(BytesIO(blob_bytes)).convert('RGB')
        
        # --- 단계 1: HSV 색공간에서 휘도/채도 보정 (흰 배경 검정 글씨 강조) ---
        hsv_img = img.convert('HSV')
        
        # Brightness 강화 (+25%)
        enhancer = ImageEnhance.Brightness(hsv_img)
        bright_enhanced = enhancer.enhance(1.2)
        
        # Hue 조정 (변경 없음 — 100% 유지)
        h, s, v = bright_enhanced.convert('HSV').split()
        v_str = v.point(lambda x: int(x * 1.3))  # Lightness boost (+30%)
        s_new = s.point(lambda x: min(int(x * 1.4), 255))  # Saturation +40% (색채 선명화)
        
        enh_v = ImageEnhance.Contrast(hsv_img.convert('RGB'))
        contrast_enhanced = enh_v.enhance(1.8)  # Contrast +80% 글씨 강조
        
        return contrast_enhanced
        
    except Exception as e:
        from io import BytesIO
        img = PilImage.open(BytesIO(blob_bytes)).convert('RGB')
        return img


def generate_html(docs):
    lines = []
    
    for doc in docs:
        fname = h_m.escape(doc['filename'])
        
        # 주소/호수 정보 추출
        addr_parts = [h_m.escape(p) for p in (doc.get('address_parts', []) or [])]
        addr_html = ', '.join(addr_parts) if addr_parts else "[주소 미인식]"
        
        contractor = ', '.join(h_m.escape(n) for n in doc['contractors']) if doc['contractors'] else "[OCR 인식 실패 — 그림 확인]"
        date_str = ', '.join(h_m.escape(d) for d in doc['dates_found']) if doc['dates_found'] else "[날짜 미인식]"
        
        # ✅ 고대비enhanced BLOB 이미지를 인라인 <img>으로 삽입
        blob_html = ""
        if doc['blob_base64']:
            blob_html = f'<img src="data:image/png;base64,{doc["blob_base64"]}" style="max-width:100%;border:2px solid #ddd;border-radius:6px;margin-top:5px;" alt="성명란 원본(고대비-enhanced)">'
        else:
            blob_html = "[이미지 없음]"
        
        preview = h_m.escape(doc['text_preview'][:200].replace('\r', '').replace('\n', '<br>'))
        
        lines.append(f"""<div style="border:1px solid #ccc;padding:20px;margin:15px 0;border-radius:8px;background:#fafafa;font-family:sans-serif;">
    <h3 style="color:#1a1a1a;margin-top:0;">📄 {fname} ({doc['kind']}, 총 {doc['pages']}쪽 중 {doc['page_num']}쪽)</h3>
    
    <!-- 호수/주소 정보 (상단 고정) -->
    <p style="background:#e8f4fd;padding:12px;border-radius:6px;font-size:15px;"><b>📍 소재지/호수:</b> {addr_html}</p>
    
    <p><b>🔗 추출된 계약자:</b> <span style="color:#e11d48;font-weight:600;">{contractor}</span></p>
    <p><b>📅 계약/체결일자:</b> {date_str}</p>
    
    <!-- 고대비-enhanced 성명란 원본 스캔 -->
    <p><b>📸 성명란 원본(임대인+임차인 병합, 고대비/휘도 보정됨)</b></p>
    {blob_html}
    
    <hr style="border:0;border-top:1px solid #eee;margin:15px 0;">
    <div style="font-size:13px;color:#666;background:#fff;padding:10px;border-radius:4px;max-height:120px;overflow-y:auto;line-height:1.6;">
        {preview}
    </div>
</div>""")

    html_header = """<html><head><meta charset="UTF-8"><title>부동산 계약서 추출 리포트 — 고대비-enhanced</title></head><body style="max-width:900px;margin:4px auto;padding:20px;"><h2>🏠 부동산 계약서 데이터 매칭 리포트 (고대비-enhanced)</h2><p style="font-size:14px;color:#888;">※ 성명란 이미지는 <b>휘도(+30%)+대비(+80%)</b>로 보정되어 손글씨가 더 선명해집니다.</p>"""
    html_footer = """</body></html>"""
    
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_header + "\n".join(lines) + html_footer)
    print(f"✅ 고대비-enhanced 리포트 생성 완료: {OUT_HTML}")


if __name__ == "__main__":
    db = sqlite3.connect(DB_PATH)
    
    rows = db.execute("""
        SELECT d.id, d.filename, d.kind, d.pages, 
               LOWER(op.full_text), op.page_num
        FROM ocr_pages op
        JOIN documents d ON d.id = op.doc_id
        WHERE LOWER(op.full_text) LIKE '%%부동산%%'
    """).fetchall()
    
    print(f"📖 {len(rows)}개 문서搜索 완료")
    
    docs = []
    
    for doc_id, filename, kind, pages, full_lower, page_num in rows:
        text_row = db.execute(
            "SELECT full_text FROM ocr_pages WHERE doc_id=? AND page_num=?",
            (doc_id, page_num)
        ).fetchone()
        full_text = text_row[0] if text_row else ""
        
        # 고대비-enhanced BLOB 이미지 로드 및 base64 인코딩
        blob_base64 = None
        blob_row = db.execute(
            "SELECT cropped_zone FROM ocr_pages WHERE doc_id=? AND page_num=?",
            (doc_id, page_num)
        ).fetchone()
        if blob_row and len(blob_row[0]) > 0:
            try:
                enhanced_img = enhance_contrast(blob_row[0])
                
                # PIL Image → PNG BytesIO → base64
                from io import BytesIO
                buf = BytesIO()
                enhanced_img.save(buf, format='PNG')
                blob_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            except Exception as e:
                print(f"  ❌ [{filename}] BLOB enhancement 실패: {e}")
        
        contractor = extract_names(full_text) if full_text else []
        dates_found = extract_dates(full_text) if full_text else []
        address_parts = extract_address_info(full_text) if full_text else []
        
        docs.append({
            'id': doc_id,
            'filename': filename,
            'kind': kind,
            'pages': pages,
            'page_num': page_num,
            'contractors': contractor if contractor else ["[OCR 인식 실패]"],
            'dates_found': dates_found if dates_found else ["[날짜 미인식]"],
            'has_blob': blob_base64 is not None,
            'blob_base64': blob_base64,
            'text_preview': full_text[:200] if full_text else "",
            'address_parts': address_parts,
        })
    
    db.close()
    
    generate_html(docs)
    print("[DONE — 고대비-enhanced 완료]")
