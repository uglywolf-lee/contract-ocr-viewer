#!/usr/bin/env python3
"""
OCR 계약서 통합 검색 및 관리 서버 (마스터 최종 복구 버전)
- 포트: 8085
- 기능: 파일명 변경, OCR 텍스트 실시간 저장, 정적 이미지/PDF 철통 서빙
"""
import http.server
import json
import os
import sqlite3
import urllib.parse

DB_PATH   = "/Users/uglywolf/.hermes/scripts/ocr_database.db"
DL_DIR    = "/Users/uglywolf/.hermes/scripts/gdrive_downloads"
HTML_PATH = "/Users/uglywolf/.hermes/scripts/comparison_viewer.html"
PORT      = 8085

class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def send_json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    # ═══════════ GET Requests ═══════════
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path
        qs     = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            if not os.path.exists(HTML_PATH):
                self.send_error(404, "HTML File Not Found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            with open(HTML_PATH, "rb") as fh:
                self.wfile.write(fh.read())
            return

        elif path == "/api/search":
            q = qs.get("q", [""])[0].strip()
            try:
                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                if q:
                    rows = conn.execute(
                        "SELECT file_id, local_path, language FROM ocr_pages WHERE ocr_text LIKE ? OR local_path LIKE ?",
                        (f"%{q}%", f"%{q}%")
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT file_id, local_path, language FROM ocr_pages LIMIT 150").fetchall()
                conn.close()
                results = [
                    {"file_id": r["file_id"], "local_path": r["local_path"], "language": r["language"]}
                    for r in rows
                ]
                self.send_json(200, {"results": results})
            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return

        elif path == "/api/ocr-text":
            file_id = qs.get("file_id", [""])[0]
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute("SELECT ocr_text FROM ocr_pages WHERE file_id = ?", (file_id,)).fetchone()
            conn.close()
            if not row:
                self.send_json(404, {"error": "Not Found"})
                return
            self.send_json(200, {"ocr_text": row[0]})
            return

        elif path.startswith("/gdrive_downloads/"):
            rel = urllib.parse.unquote(path[len("/gdrive_downloads/"):])
            safe = os.path.basename(rel)
            full = os.path.join(DL_DIR, safe)
            
            if not os.path.exists(full):
                try:
                    files = os.listdir(DL_DIR)
                    matched = [f for f in files if safe.split('.')[0] in f]
                    if matched:
                        full = os.path.join(DL_DIR, matched[0])
                    else:
                        self.send_error(404, "File Not Found: " + safe)
                        return
                except Exception as e:
                    self.send_error(404, "Directory Error: " + str(e))
                    return

            lower_safe = full.lower()
            if lower_safe.endswith('.pdf'):
                content_type = 'application/pdf'
            elif lower_safe.endswith('.jpg') or lower_safe.endswith('.jpeg'):
                content_type = 'image/jpeg'
            elif lower_safe.endswith('.png'):
                content_type = 'image/png'
            else:
                content_type = 'image/jpeg' if 'jpg' in lower_safe else 'application/pdf'

            try:
                with open(full, "rb") as fh:
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    safe_encoded = urllib.parse.quote(os.path.basename(full))
                    self.send_header("Content-Disposition", "inline; filename*=UTF-8''" + safe_encoded)
                    self.send_header("Content-Length", str(os.path.getsize(full)))
                    self.end_headers()
                    self.wfile.write(fh.read())
            except Exception as e:
                self.send_error(500, "File read error: " + str(e))
            return

    # ═══════════ POST Requests ═══════════
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            payload_raw = self.rfile.read(content_length)
            payload = json.loads(payload_raw.decode('utf-8'))
        except Exception as e:
            self.send_json(400, {"success": False, "message": "Invalid JSON Payload"})
            return

        if path == "/api/rename-file":
            try:
                file_id = payload.get("file_id", "")
                new_name = payload.get("new_name", "").strip()
                
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                row = cur.execute("SELECT file_id, local_path FROM ocr_pages WHERE file_id = ?", (file_id,)).fetchone()
                
                if not row:
                    conn.close()
                    self.send_json(404, {"success": False, "message": "DB에 문서가 없습니다."})
                    return
                
                old_fid, old_local = row
                new_dir = os.path.dirname(old_local) or DL_DIR
                new_full_path = os.path.join(new_dir, new_name)
                
                actual_old_local = old_local
                if not os.path.exists(actual_old_local):
                    actual_old_local = os.path.join(DL_DIR, os.path.basename(old_local))
                    if not os.path.exists(actual_old_local):
                        files = os.listdir(DL_DIR)
                        matched = [f for f in files if old_fid.split('.')[0] in f]
                        if matched:
                            actual_old_local = os.path.join(DL_DIR, matched[0])
                        else:
                            conn.close()
                            self.send_json(404, {"success": False, "message": "디스크에 원본 파일이 없습니다."})
                            return

                os.rename(actual_old_local, new_full_path)
                cur.execute("UPDATE ocr_pages SET file_id = ?, local_path = ? WHERE file_id = ?", (new_name, new_full_path, old_fid))
                conn.commit()
                conn.close()
                
                self.send_json(200, {"success": True, "new_file_id": new_name, "new_local_path": new_full_path})
            except Exception as e:
                self.send_json(500, {"success": False, "message": str(e)})
            return

        elif path == "/api/update-ocr":
            file_id = payload.get("file_id", "")
            ocr_text = payload.get("ocr_text", "")
            
            if not file_id:
                self.send_json(400, {"success": False, "message": "file_id 인자가 누락되었습니다."})
                return
            
            try:
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                row = cur.execute("SELECT 1 FROM ocr_pages WHERE file_id = ?", (file_id,)).fetchone()
                if not row:
                    conn.close()
                    self.send_json(404, {"success": False, "message": "DB에 일치하는 파일이 없습니다."})
                    return
                
                cur.execute("UPDATE ocr_pages SET ocr_text = ? WHERE file_id = ?", (ocr_text, file_id))
                conn.commit()
                conn.close()
                self.send_json(200, {"success": True, "message": "OCR 수정 완료"})
            except Exception as e:
                self.send_json(500, {"success": False, "message": str(e)})
            return
        
        else:
            self.send_error(404, "Not Found")

if __name__ == "__main__":
    server = http.server.HTTPServer(("", PORT), Handler)
    print("🚀 마스터 서버가 포트 {}에서 정상 가동 중입니다...".format(PORT))
    server.serve_forever()
