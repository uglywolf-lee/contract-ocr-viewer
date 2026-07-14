#!/usr/bin/env python3
"""부동산 임대차 임차인 관리 서버 — 포트 8086"""
import http.server, json, sqlite3, urllib.parse, os, time, re, traceback, mimetypes

DB_PATH = "/Users/uglywolf/.hermes/scripts/tenant_manager.db"
HTML_PATH = "/Users/uglywolf/.hermes/scripts/tenant_manager.html"
PORT = 8086

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass

    def send_json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length)) if length else {}

    # ─── GET routes ───
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        # API가 아닌 경로는 정적 파일 자동 처리
        if not path.startswith("/api/"):
            self._serve_static(path)
            return

        try:
            if path == "/api/db":
                conn = get_conn()
                tables = {}
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                    tname = r[0]
                    cols = [c['name'] for c in conn.execute(f"PRAGMA table_info({tname})").fetchall()]
                    tables[tname] = {"columns": cols}
                conn.close()
                self.send_json(200, {"tables": tables})

            elif path == "/api/tenants":
                limit = int(qs.get("limit", ["50"])[0])
                conn = get_conn()
                rows = conn.execute(f"SELECT * FROM tenants ORDER BY name LIMIT {limit}").fetchall()
                conn.close()
                self.send_json(200, {"tenants": [dict(r) for r in rows]})

            elif path == "/api/tenants/search":
                q = qs.get("q", [""])[0].strip()
                conn = get_conn()
                rows = conn.execute(
                    "SELECT * FROM tenants WHERE name LIKE ? OR contact_phone LIKE ? ORDER BY name",
                    (f"%{q}%", f"%{q}%")
                ).fetchall()
                conn.close()
                self.send_json(200, {"tenants": [dict(r) for r in rows]})

            elif path.startswith("/api/tenant/"):
                tenant_id = path.split("/")[3]
                conn = get_conn()
                c = conn.execute("SELECT * FROM tenants WHERE id=?", (tenant_id,)).fetchone()
                if not c:
                    conn.close(); self.send_json(404, {"error":"tenant not found"}); return
                contracts = conn.execute("SELECT * FROM contracts WHERE tenant_id=? ORDER BY contract_end DESC", (tenant_id,)).fetchall()
                maint = conn.execute("SELECT m.*, t.name as tenant_name FROM maintenance_log m JOIN tenants t ON m.tenant_id=t.id WHERE m.tenant_id=? ORDER BY issue_date DESC LIMIT 50", (tenant_id,)).fetchall()
                arrears = conn.execute("SELECT * FROM arrears_log WHERE tenant_id=? AND status IS NOT NULL ORDER BY due_date DESC", (tenant_id,)).fetchall()
                conn.close()
                self.send_json(200, {
                    "tenant": dict(c),
                    "contracts": [dict(r) for r in contracts],
                    "maintenance": [dict(r) for r in maint],
                    "arrears": [dict(r) for r in arrears]
                })

            elif path.startswith("/api/contract/"):
                cid = path.split("/")[3]
                conn = get_conn()
                c = conn.execute("SELECT * FROM contracts WHERE id=?", (cid,)).fetchone()
                conn.close()
                self.send_json(200, {"contract": dict(c) if c else None})

            elif path.startswith("/api/maintenance/"):
                mid = path.split("/")[3]
                conn = get_conn()
                m = conn.execute("SELECT * FROM maintenance_log WHERE id=?", (mid,)).fetchone()
                conn.close()
                self.send_json(200, {"maintenance": dict(m) if m else None})

            # [교정] if를 elif로 복구하여 API 라우팅 독점권 보장
            elif path == "/api/stats":
                conn = get_conn()
            
                # 인덱스 [0] 접근 — 대소문자 키 충돌 원천 차단 (KeyError 방지)
                total_tenants = conn.execute("SELECT COUNT(*) FROM tenants").fetchone()[0]
                active_contracts = conn.execute("SELECT COUNT(*) FROM contracts WHERE contract_end >= date('now')").fetchone()[0]
            
                renewal_soon_rows = conn.execute("""
                    SELECT COUNT(*) FROM contracts 
                    WHERE renewal_flag = '재계약예정'
                      AND contract_end BETWEEN date('now') AND date('now', '+90 days')
                """).fetchone()[0]
            
                total_deposits = conn.execute("SELECT COALESCE(SUM(deposit_won), 0) FROM contracts").fetchone()[0]
                total_rent = conn.execute("SELECT COALESCE(SUM(monthly_rent_won), 0) FROM contracts").fetchone()[0]
            
                arrestees_count = conn.execute("""
                    SELECT COUNT(DISTINCT a.tenant_id) 
                    FROM arrears_log a
                    JOIN contracts c ON a.contract_id = c.id
                    WHERE julianday(a.due_date) - julianday('now') < -30
                """).fetchone()[0]
            
                conn.close()
            
                s = {
                    "total_tenants": total_tenants,
                    "active_contracts": active_contracts,
                    "renewal_soon": renewal_soon_rows,
                    "total_deposits_won": total_deposits,
                    "total_monthly_income_won": total_rent,
                    "arrestees_count": arrestees_count,
                }
            
                self.send_json(200, s)

            else:
                self.send_error(404)
        except Exception as e:
            self.send_json(500, {"error": str(e), "trace": traceback.format_exc()})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            body = self.read_body()
        except Exception:
            self.send_json(400, {"error":"bad json"})
            return

        if path == "/api/tenant":          # ─── POST tenant create/update ──
            conn = get_conn()
            t = body.get("tenant", {})
            tid = t.get("id") or f"T-{int(time.time())%100000:05d}{int(time.time()*100)%100:02d}"
            
            if t.get("id"):
                conn.execute("""UPDATE tenants SET name=?, contact_phone=?, personal_id=?, 
                    emergency_contact=?, representative_name=?, address=?, updated_at=datetime('now','localtime')
                    WHERE id=?""", (t["name"], t.get("contact_phone"), t.get("personal_id"),
                        t.get("emergency_contact"), t.get("representative_name"), t.get("address"), t["id"]))
                print(f"✓ Updated tenant {t['id']}")
            else:
                conn.execute("""INSERT INTO tenants(id,name,contact_phone,personal_id,emergency_contact,representative_name,address)
                    VALUES(?,?,?,?,?,?,?)""", (tid,t["name"], t.get("contact_phone"), t.get("personal_id"),
                        t.get("emergency_contact"), t.get("representative_name"), t.get("address","")))
                print(f"✓ Created tenant {tid}")
            conn.commit(); conn.close()
            self.send_json(200, {"ok": True, "id": tid})
            return

        elif path == "/api/contract":       # ─── POST contract create/update ──
            conn = get_conn()
            c = body.get("contract", {})
            cid = c.get("id") or f"C-{int(time.time())%100000:05d}{int(time.time()*100)%100:02d}"
            
            if c.get("id"):
                conn.execute("""UPDATE contracts SET tenant_id=?, contract_type=?, deposit_won=?, monthly_rent_won=?,
                    property_sheets=?, contract_start=?, contract_end=?, actual_deposit_date=?,
                    midas_payment=?, renewal_flag=?, penalty_rate_pct=?, note=?, updated_at=datetime('now','localtime')
                    WHERE id=?""", (c["tenant_id"], c.get("contract_type"), c.get("deposit_won",0), 
                        c.get("monthly_rent_won",0), c.get("property_sheets",""), c.get("contract_start",""),
                        c.get("contract_end",""), c.get("actual_deposit_date",""), c.get("midas_payment",0),
                        c.get("renewal_flag","미정"), c.get("penalty_rate_pct",30.0), c.get("note",""), c["id"]))
            else:
                conn.execute("""INSERT INTO contracts(id,tenant_id,contract_type,deposit_won,monthly_rent_won,
                    property_sheets,contract_start,contract_end,actual_deposit_date,mid_payment,renewal_flag,
                    penalty_rate_pct,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    cid, c["tenant_id"], c.get("contract_type",""), c.get("deposit_won",0),
                    c.get("monthly_rent_won",0), c.get("property_sheets",""), c.get("contract_start",""),
                    c.get("contract_end",""), c.get("actual_deposit_date",""), 0,
                    c.get("renewal_flag","미정"), c.get("penalty_rate_pct",30.0), c.get("note","")))
            conn.commit(); conn.close()
            self.send_json(200, {"ok": True, "id": cid})
            return

        elif path == "/api/maintenance":    # ─── POST maintenance create/update ──
            conn = get_conn()
            m = body.get("maintenance", {})
            mid = m.get("id") or f"M-{int(time.time())%10000:04d}{int(time.time()*100)%100:02d}"
            
            if m.get("id"):
                conn.execute("""UPDATE maintenance_log SET tenant_id=?, property_no=?, request_type=?,
                    issue_date=?, resolved_at=?, repair_cost=?, status=?, detail=? WHERE id=?""", (
                    m["tenant_id"], m.get("property_no",""), m.get("request_type",""), 
                    m.get("issue_date",""), m.get("resolved_at",""), m.get("repair_cost",0),
                    m.get("status","요청완료"), m.get("detail",""), m["id"]))
            else:
                conn.execute("""INSERT INTO maintenance_log(id,tenant_id,property_no,request_type,issue_date,
                    resolved_at,repair_cost,status,detail) VALUES(?,?,?,?,?,?,?,?,?)""", (
                    mid, m["tenant_id"], m.get("property_no",""), m.get("request_type",""),
                    m.get("issue_date",""), m.get("resolved_at",""), m.get("repair_cost",0),
                    m.get("status","요청완료"), m.get("detail","")))
            conn.commit(); conn.close()
            self.send_json(200, {"ok": True, "id": mid})
            return

        elif path == "/api/arrears":        # ─── POST arrears create/update ──
            conn = get_conn()
            a = body.get("arrears", {})
            aid = a.get("id") or f"A-{int(time.time())%10000:04d}{int(time.time()*100)%100:02d}"
            
            if a.get("id"):
                conn.execute("""UPDATE arrears_log SET contract_id=?, tenant_id=?, due_date=?, actual_date=?,
                    amount=?, days_late=?, penalty_won=?, note=? WHERE id=?""", (
                    a.get("contract_id",""), a["tenant_id"], a.get("due_date",""), a.get("actual_date",""),
                    a.get("amount",0), a.get("days_late",0), a.get("penalty_won",0), a.get("note",""), a["id"]))
            else:
                conn.execute("""INSERT INTO arrears_log(id,contract_id,tenant_id,due_date,actual_date,
                    amount,days_late,penalty_won,note) VALUES(?,?,?,?,?,?,?,?,?)""", (
                    aid, a.get("contract_id",""), a["tenant_id"], a.get("due_date",""), 
                    a.get("actual_date",""), a.get("amount",0), a.get("days_late",0),
                    a.get("penalty_won",0), a.get("note","")))
            conn.commit(); conn.close()
            self.send_json(200, {"ok": True, "id": aid})
            return

        else:
            self.send_error(404)
            return

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        if path.startswith("/api/tenant/"):
            tid = path.split("/")[3]
            # cascade delete contracts → maintenance → arrears
            conn = get_conn()
            conn.execute("DELETE FROM arrears_log WHERE tenant_id=?", (tid,))
            conn.execute("DELETE FROM maintenance_log WHERE tenant_id=?", (tid,))
            contract_ids = [r[0] for r in conn.execute("SELECT id FROM contracts WHERE tenant_id=?", (tid,)).fetchall()]
            if contract_ids:
                placeholders = ",".join(f"'{cid}'" for cid in contract_ids)
                conn.execute(f"DELETE FROM arrears_log WHERE contract_id IN ({placeholders})")
            conn.execute("DELETE FROM contracts WHERE tenant_id=?", (tid,))
            conn.execute("DELETE FROM tenants WHERE id=?", (tid,))
            conn.commit(); conn.close()
            self.send_json(200, {"ok": True, "deleted": tid})

        elif path.startswith("/api/contract/"):
            cid = path.split("/")[3]
            conn = get_conn()
            # 먼저 tenant_id 가져오기
            tenant_id = conn.execute("SELECT tenant_id FROM contracts WHERE id=?", (cid,)).fetchone()["tenant_id"]
            conn.execute("DELETE FROM contracts WHERE id=?", (cid,))
            conn.commit(); conn.close()
            self.send_json(200, {"ok": True})

        elif path.startswith("/api/maintenance/"):
            mid = path.split("/")[3]
            conn = get_conn()
            conn.execute("DELETE FROM maintenance_log WHERE id=?", (mid,))
            conn.commit(); conn.close()
            self.send_json(200, {"ok": True})

        elif path.startswith("/api/arrears/"):
            aid = path.split("/")[3]
            conn = get_conn()
            conn.execute("DELETE FROM arrears_log WHERE id=?", (aid,))
            conn.commit(); conn.close()
            self.send_json(200, {"ok": True})

        else:
            self.send_error(404)

    def send_file(self, path, ctype):
        if not os.path.exists(path):
            self.send_error(404)
            return
        self.send_response(200); self.send_header("Content-Type", ctype); self.end_headers()
        with open(path, "rb") as f: self.wfile.write(f.read())

    def _serve_static(self, url_path):
        """정적 파일 자동 서빙 — HTML/JS/CSS/이미지 등"""
        if url_path in ('/', '', '/tenant_manager.html'):
            self.send_file(HTML_PATH, 'text/html; charset=utf-8')
            return

        base_dir = "/Users/uglywolf/.hermes/scripts"
        file_name = os.path.basename(urllib.parse.unquote(url_path))
        file_path = os.path.join(base_dir, file_name)
        mime, _ = mimetypes.guess_type(file_path)
        if not mime:
            if file_name.endswith('.js'): mime = 'application/javascript'
            elif file_name.endswith('.css'): mime = 'text/css'
            else: mime = 'application/octet-stream'
        
        if 'javascript' in mime or 'text' in mime:
            ct = f"{mime}; charset=utf-8"
        else:
            ct = mime
        self.send_file(file_path, ct)

if __name__ == "__main__":
    print(f"📡 tenant_manager server on port {PORT}")
    httpd = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    httpd.serve_forever()
