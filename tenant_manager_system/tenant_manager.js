/* tenant_manager.js — 임대인 관리 시스템 로직 */
const API = (p) => '/api' + (p.startsWith('/') ? p : '/' + p);
let currentTenantId = null;
let allTenants = [];

// 싱글톤 메모리 최적화 문자열 이스케이프 함수
const esc = (() => {
    const d = document.createElement('div');
    return (s) => { if(!s) return ''; d.textContent = s; return d.innerHTML; };
})();

// ═══ 모달 HTML 템플릿 저장소 (에이전트 매핑 대응) ═══
const MODAL_TEMPLATES = {
    tenant: (subData) => `<div class="fg" data-agent-form="tenant">
        <div class="fl"><label>상호/성명</label><input id="ml_name" data-agent="tenant-name" value="${subData?.name || ''}"></div>
        <div class="fl"><label>연락처</label><input id="ml_phone" data-agent="tenant-phone" value="${subData?.contact_phone || ''}"></div>
        <div class="fl"><label>사업자/주민번호</label><input id="ml_id" data-agent="tenant-personal-id" value="${subData?.personal_id || ''}"></div>
        <div class="fl"><label>긴급연락처</label><input id="ml_emergency" data-agent="tenant-emergency" value="${subData?.emergency_contact || ''}"></div>
        <div class="fl"><label>대표자</label><input id="ml_rep" data-agent="tenant-rep" value="${subData?.representative_name || ''}"></div>
        <div class="fl"><label>주소</label><textarea id="ml_addr" data-agent="tenant-address">${subData?.address || ''}</textarea></div>
    </div>
    <div class="fa">
        <button class="btn btn-primary" data-agent="save-btn" onclick="doSaveTenant(${!!subData})">저장</button>
        <button class="btn btn-sm btn-danger" onclick="closeModal()">취소</button>
    </div>`,

    contract: (subData, currentId) => `<div class="fg" data-agent-form="contract">
        <div class="fl"><label>임차인ID</label><input id="ml_tenant" data-agent="contract-tenant-id" value="${subData?.tenant_id || currentId || ''}"></div>
        <div class="fl"><label>유형</label><select id="ml_type" data-agent="contract-type">${['주택전세','주택월세','상가전세','상가월세','오피스','창고'].map(x=>`<option ${subData?.contract_type===x?'selected':''}>${x}</option>`).join('')}</select></div>
        <div class="fl"><label>목적지(호수)</label><input id="ml_property" data-agent="contract-property" value="${subData?.property_sheets || ''}"></div>
        <div class="fl"><label>보증금(원)</label><input id="ml_deposit" data-agent="contract-deposit" value="${subData?.deposit_won || 0}" type="number"></div>
        <div class="fl"><label>월세(원)</label><input id="ml_rent" data-agent="contract-rent" value="${subData?.monthly_rent_won || 0}"></div>
        <div class="fl"><label>계약시작</label><input id="ml_start" data-agent="contract-start" type="date" value="${subData?.contract_start || ''}"></div>
        <div class="fl"><label>계약만료</label><input id="ml_end" data-agent="contract-end" type="date" value="${subData?.contract_end || ''}"></div>
        <div class="fl"><label>실제입금일</label><input id="ml_deposit_date" data-agent="contract-actual-deposit-date" type="date" value="${subData?.actual_deposit_date || ''}"></div>
        <div class="fl"><label>갱신상태</label><select id="ml_renewal" data-agent="contract-renewal">${['미정','재계약예정','재계약거절'].map(x=>`<option ${subData?.renewal_flag===x?'selected':''}>${x}</option>`).join('')}</select></div>
        <div class="fl"><label>위약금율(%)</label><input id="ml_penalty" data-agent="contract-penalty-rate" value="${subData?.penalty_rate_pct || 30}" type="number"></div>
        <div class="fl" style="grid-column:1/-1"><label>특약사항</label><textarea id="ml_note" data-agent="contract-note">${subData?.note || ''}</textarea></div>
    </div>
    <div class="fa">
        <button class="btn btn-primary" data-agent="save-btn" onclick="doSaveContract(${!!subData})">저장</button>
        <button class="btn btn-sm btn-danger" onclick="closeModal()">취소</button>
    </div>`,

    maintenance: (subData, currentId) => `<div class="fg" data-agent-form="maintenance">
        <div class="fl"><label>임차인ID</label><input id="ml_tenant" data-agent="maint-tenant-id" value="${subData?.tenant_id || currentId}"></div>
        <div class="fl"><label>호수/위치</label><input id="ml_prop" data-agent="maint-property-no" value="${subData?.property_no || ''}"></div>
        <div class="fl"><label>유형</label><select id="ml_maint_type" data-agent="maint-type">${['배관','난방','전기','도배','장판','엘리베이터','소방설비','기타'].map(x=>`<option ${subData?.request_type===x?'selected':''}>${x}</option>`).join('')}</select></div>
        <div class="fl"><label>발생일</label><input id="ml_mdate" data-agent="maint-issue-date" type="date" value="${subData?.issue_date || ''}"></div>
        <div class="fl"><label>처리일</label><input id="ml_rdate" data-agent="maint-resolved-date" type="date" value="${subData?.resolved_at || ''}"></div>
        <div class="fl"><label>비용(원)</label><input id="ml_mcost" data-agent="maint-cost" value="${subData?.repair_cost || 0}" type="number"></div>
        <div class="fl"><label>상태</label><select id="ml_mstatus" data-agent="maint-status">${['요청완료','처리중','거절'].map(x=>`<option ${subData?.status===x?'selected':''}>${x}</option>`).join('')}</select></div>
        <div class="fl" style="grid-column:1/-1"><label>상세내역</label><textarea id="ml_mdetail" data-agent="maint-detail">${subData?.detail || ''}</textarea></div>
    </div>
    <div class="fa">
        <button class="btn btn-primary" data-agent="save-btn" onclick="doSaveMaintenance(${!!subData})">저장</button>
        <button class="btn btn-sm btn-danger" onclick="closeModal()">취소</button>
    </div>`,

    arrears: (subData, currentId) => `<div class="fg" data-agent-form="arrears">
        <div class="fl"><label>임차인ID</label><input id="ml_ar_tenant" data-agent="arrears-tenant-id" value="${subData?.tenant_id || currentId}"></div>
        <div class="fl"><label>계약ID</label><input id="ml_ar_contract" data-agent="arrears-contract-id" value="${subData?.contract_id || ''}"></div>
        <div class="fl"><label>납부예정날짜</label><input id="ml_ar_due" data-agent="arrears-due-date" type="date" value="${subData?.due_date || ''}"></div>
        <div class="fl"><label>실제입금날짜</label><input id="ml_ar_actual" data-agent="arrears-actual-date" type="date" value="${subData?.actual_date || ''}"></div>
        <div class="fl"><label>금액(원)</label><input id="ml_ar_amount" data-agent="arrears-amount" value="${subData?.amount || 0}" type="number"></div>
        <div class="fl"><label>연체일수</label><input id="ml_ar_late" data-agent="arrears-days-late" value="${subData?.days_late || 0}" type="number"></div>
        <div class="fl"><label>위약금(원)</label><input id="ml_ar_penalty" data-agent="arrears-penalty" value="${subData?.penalty_won || 0}" type="number"></div>
        <div class="fl" style="grid-column:1/-1"><label>비고</label><textarea id="ml_ar_note" data-agent="arrears-note">${subData?.note || ''}</textarea></div>
    </div>
    <div class="fa">
        <button class="btn btn-primary" data-agent="save-btn" onclick="doSaveArrears(${!!subData})">저장</button>
        <button class="btn btn-sm btn-danger" onclick="closeModal()">취소</button>
    </div>`
};

// ═══ INIT ═══
(async function init() { await loadStats(); await loadTenants(); })();
setInterval(loadStats, 60000);

document.getElementById('modal-overlay').addEventListener('click', (e) => { 
    if (e.target.id === 'modal-overlay') closeModal(); 
});

/* ═══ Stats Panel ═══ */
async function loadStats() {
    try {
        const r = await fetch(API('/stats'));
        const d = await r.json();
        document.getElementById('statsBar').innerHTML = `
            <div class="stat-box"><div class="num">${d.total_tenants}</div><div class="lbl">임차인</div></div>
            <div class="stat-box"><div class="num">${d.active_contracts}</div><div class="lbl">계약중</div></div>
            <div class="stat-box" style="color:var(--amber)"><div class="num">${d.renewal_soon}</div><div class="lbl">90日內갱신</div></div>
            <div class="stat-box"><div class="num" style="color:var(--success)">${((d.total_deposits_won || 0) / 1e4).toFixed(0)}</div><div class="lbl">보증합계(만원)</div></div>
            <div class="stat-box"><div class="num" style="color:var(--danger)">${d.arrestees_count}</div><div class="lbl">연체30일+</div></div>`;
    } catch(e) { console.error('loadStats error', e); }
}

/* ═══ Tenants List ═══ */
async function loadTenants() {
    try {
        const r = await fetch(API('/tenants?limit=999'));
        const d = await r.json();
        allTenants = d.tenants || [];
        renderTenantList(allTenants);
    } catch(e) { console.error('loadTenants error', e); }
}

async function doSearch() {
    const q = document.getElementById('searchInput').value.trim();
    if (!q) { allTenants = await _fetchAllTenants(); renderTenantList(allTenants); return; }
    try {
        const r = await fetch(API('/tenants/search?q=' + encodeURIComponent(q)));
        const d = await r.json();
        renderTenantList(d.tenants || []);
    } catch(e) { console.error('search error', e); }
}

async function _fetchAllTenants() {
    try { const r = await fetch(API('/tenants?limit=999')); return (await r.json()).tenants || []; }
    catch(e) { return []; }
}

function renderTenantList(list) {
    const el = document.getElementById('tenantList');
    if (!list.length) { 
        el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--muted)">임차인 없음<br>＋ 버튼으로 추가</div>'; 
        return; 
    }
    el.innerHTML = '';
    const frag = document.createDocumentFragment();
    list.forEach(t => {
        const item = document.createElement('div');
        item.className = 'tenant-item' + (currentTenantId === t.id ? ' active' : '');
        item.dataset.tenantId = t.id;
        item.dataset.agentForm = 'tenant-list';
        item.onclick = () => selectTenant(t.id);
        
        const nameEl = document.createElement('div');
        nameEl.className = 'ti-name';
        nameEl.textContent = t.name;
        
        const subEl = document.createElement('div');
        subEl.className = 'ti-sub';
        subEl.innerHTML = `<span>${t.contact_phone || '연락처없음'}</span>`;
        
        if (t.personal_id) {
            const idSpan = document.createElement('div');
            idSpan.textContent = t.personal_id;
            idSpan.dataset.agentField = 'personal-id';
            subEl.appendChild(idSpan);
        }
        
        item.appendChild(nameEl);
        item.appendChild(subEl);
        frag.appendChild(item);
    });
    el.appendChild(frag);
}

/* ═══ Select Tenant ═══ */
async function selectTenant(id) {
    currentTenantId = id;
    try {
        const r = await fetch(API('/tenant/' + encodeURIComponent(id)));
        if (r.status === 404) { loadTenants(); return; }
        const d = await r.json();
        
        document.querySelectorAll('.tenant-item.active').forEach(el => el.classList.remove('active'));
        const match = Array.from(document.querySelectorAll('[data-agent-form="tenant-list"]'))
            .find(el => el.dataset.tenantId === id);
        if (match) {
            match.classList.add('active');
            match.scrollIntoView({ block: 'nearest', inline: 'start' });
        }
        renderTenantDetail(d);
    } catch(e) { console.error('selectTenant error', e); }
}

/* ═══ Render Tenant Detail ═══ */
function renderTenantDetail(data) {
    const t = data.tenant; if (!t) return;
    const main = document.getElementById('mainPanel');
    const soonCount = (data.contracts || []).filter(c => {
        const e = new Date(c.contract_end);
        return e >= new Date() && e <= new Date(Date.now() + 90 * 86400000);
    }).length;

    let html = `<div class="tabs">
        <button class="tab active" data-idx="0" data-agent="tenant-info">임차인정보</button>
        <button class="tab" data-idx="1" data-agent="contract-list">계약${data.contracts?.length ? '('+ data.contracts.length + ')' : ''}</button>
        <button class="tab" data-idx="2" data-agent="maintenance-log">수리/관리${data.maintenance?.length ? '('+ data.maintenance.length + ')' : ''}</button>
        <button class="tab" data-idx="3" data-agent="arrears-history">연체이력</button>
        <span style="font-size:13px; margin-left:auto; padding-top:12px; font-weight:700; color:var(--accent)">임차인: ${esc(t.name)}</span>
    </div>`;

    // Tab 0: Tenant info
    html += `<div class="tc-panel active" data-tab="0">
        <div style="display:flex;justify-content:space-between;margin-bottom:16px"><h2>${esc(t.name)}</h2><div>
            <button class="btn btn-sm" onclick="openModal('tenant', null, ${JSON.stringify(t).replace(/'/g, "\\'")})">수정</button>
            <button class="btn btn-sm btn-danger" onclick="deleteTenant('${t.id}')">삭제</button></div></div>
        <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
            ${t.contact_phone ? '<span class="badge bg">' + esc(t.contact_phone) + '</span>' : ''}
            ${t.personal_id ? '<span class="badge bb">' + esc(t.personal_id) + '</span>' : ''}
            ${t.emergency_contact ? '<span class="badge ba">긴급: ' + esc(t.emergency_contact) + '</span>' : ''}
            ${soonCount ? '<span class="badge br">' + soonCount + '건 만료임박</span>' : ''}
        </div>
        <div class="sec"><h3>기본정보</h3><input type="hidden" id="ft_id" value="${esc(t.id)}">
            <div class="fg" data-agent-form="tenant-static">
                <div class="fl"><label>상호/성명</label><input id="ft_name" data-agent="static-name" value="${esc(t.name)}"></div>
                <div class="fl"><label>연락처</label><input id="ft_phone" data-agent="static-phone" value="${esc(t.contact_phone || '')}"></div>
                <div class="fl"><label>사업자/주민번호</label><input id="ft_id2" data-agent="static-personal-id" value="${esc(t.personal_id || '')}"></div>
                <div class="fl"><label>긴급연락처</label><input id="ft_emergency" data-agent="static-emergency" value="${esc(t.emergency_contact || '')}"></div>
                <div class="fl"><label>대표자</label><input id="ft_rep" data-agent="static-rep" value="${esc(t.representative_name || '')}"></div>
                <div class="fl"><label>주소</label><textarea id="ft_addr" data-agent="static-address">${esc(t.address || '')}</textarea></div>
            </div>
            <div class="fa"><button class="btn btn-primary" onclick="saveTenant('${t.id}')">저장</button></div>
        </div>
    </div>`;

    // Tab 1: Contracts
    const ct = (data.contracts || []);
    html += `<div class="tc-panel" data-tab="1">
        <div style="display:flex;justify-content:space-between;margin-bottom:12px"><h3>📋 계약목록 (${ct.length})</h3><button class="btn btn-sm btn-primary" onclick="openModal('contract')">＋계약추가</button></div>`;
    if (ct.length) {
        html += `<table class="dt"><thead><tr><th>유형</th><th>목적지</th><th>보증금(만원)</th><th>월세(만원)</th><th>기간</th><th>갱신</th><th>잔여일</th><th></th></tr></thead><tbody>`;
        ct.forEach(c => {
            const ld = c.contract_end ? Math.round((new Date(c.contract_end) - Date.now()) / 86400000) : '—';
            const rClass = c.renewal_flag === '재계약거절' ? 'br' : c.renewal_flag === '재계약예정' ? 'ba' : 'bg';
            html += `<tr>
                <td><span class="badge bb">${esc(c.contract_type || '-')}</span></td>
                <td>${esc(c.property_sheets || '-')}</td>
                <td style="font-weight:700;color:var(--success)">${(c.deposit_won || 0) / 1e4 > 9999 ? ((c.deposit_won || 0) / 1e8).toFixed(1) + '억' : (c.deposit_won || 0) / 1e4 + '만'}</td>
                <td style="font-weight:700;color:var(--amber)">${(c.monthly_rent_won || 0) / 1e4 > 9999 ? ((c.monthly_rent_won || 0) / 1e8).toFixed(1) + '억' : (c.monthly_rent_won || 0) / 1e4 + '만'}</td>
                <td>${esc(c.contract_start || '—')} → ${esc(c.contract_end || '—')}</td>
                <td><span class="badge ${rClass}">${esc(c.renewal_flag)}</span></td>
                <td style="color:${ld < 180 && ld > 0 ? 'var(--danger)' : 'var(--text)'}">${typeof ld === 'number' ? ld + '일' : ld}</td>
                <td><button class="btn btn-sm" onclick="openModal('contract', null, ${JSON.stringify(c).replace(/'/g, "\\'")})">수정</button></td>
            </tr>`;
        });
        html += '</tbody></table>';
    } else { html += '<p style="color:var(--muted);padding:20px;text-align:center">계약 없음</p>'; }
    html += `</div>`;

    // Tab 2: Maintenance
    const mat = (data.maintenance || []);
    html += `<div class="tc-panel" data-tab="2">
        <div style="display:flex;justify-content:space-between;margin-bottom:12px"><h3>🔧 수리/관리이력 (${mat.length})</h3><button class="btn btn-sm btn-primary" onclick="openModal('maintenance')">＋등록</button></div>`;
    if (mat.length) {
        html += `<table class="dt"><thead><tr><th>유형</th><th>호수</th><th>내용</th><th>발생일</th><th>상태</th><th>비용(만원)</th><th></th></tr></thead><tbody>`;
        mat.forEach(m => {
            const sClass = m.status === '처리중' ? 'ba' : m.status === '거절' ? 'br' : 'bg';
            html += `<tr><td><span class="badge bb">${esc(m.request_type || '-')}</span></td>
                <td>${esc(m.property_no || '-')}</td><td>${esc(m.detail || '-')}</td><td>${esc(m.issue_date || '—')}</td>
                <td><span class="badge ${sClass}">${esc(m.status)}</span></td>
                <td style="font-weight:700;color:var(--amber)">${m.repair_cost / 1e4 + '만'}</td>
                <td><button class="btn btn-sm" onclick="openModal('maintenance', null, ${JSON.stringify(m).replace(/'/g, "\\'")})">수정</button></td></tr>`;
        });
        html += '</tbody></table>';
    } else { html += '<p style="color:var(--muted);padding:20px;text-align:center">이력 없음</p>'; }
    html += `</div>`;

    // Tab 3: Arrears
    const ar = (data.arrears || []);
    html += `<div class="tc-panel" data-tab="3">
        <h3 style="margin-bottom:12px">💰 연체이력 (${ar.length})</h3>`;
    if (ar.length) {
        html += `<table class="dt"><thead><tr><th>계약ID</th><th>납부예정일</th><th>실제입금</th><th>금액(만원)</th><th>연체일수</th><th>위약금(만원)</th><th></th></tr></thead><tbody>`;
        ar.forEach(a => {
            const days = (a.days_late || 0);
            html += `<tr><td>${esc(a.contract_id)}</td><td>${esc(a.due_date || '—')}</td><td style="color:var(--success)">${esc(a.actual_date || '❌미입금')}</td>
                <td style="font-weight:700;color:var(--accent)">${a.amount / 1e4 + '만'}</td>
                <td><span class="badge ${days > 30 ? 'br' : days > 0 ? 'ba' : 'bg'}">${days}일</span></td>
                <td style="font-weight:700;color:var(--danger)">${a.penalty_won / 1e4 + '만'}</td>
                <td><button class="btn btn-sm" onclick="openModal('arrears', null, ${JSON.stringify(a).replace(/'/g, "\\'")})">수정</button></td></tr>`;
        });
        html += '</tbody></table>';
    } else { html += '<p style="color:var(--muted);padding:20px;text-align:center">연체 없음 ✓</p>'; }
    html += `</div>`;

    main.innerHTML = html;

    main.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            main.querySelector('.tab.active')?.classList.remove('active');
            main.querySelectorAll('.tc-panel.active')?.forEach(el => el.classList.remove('active'));
            tab.classList.add('active');
            const idx = tab.dataset.idx;
            main.querySelector(`.tc-panel[data-tab="${idx}"]`)?.classList.add('active');
        });
    });
}

// ═══ Modal Controller ═══
function openModal(type, tenantData, subData) {
    const ov = document.getElementById('modal-overlay');
    const title = document.getElementById('modal-title');
    const body = document.getElementById('modal-body');
    ov.style.display = 'flex';
    window._modalData = { type, tenantData, subData };
    title.textContent = type === 'tenant' ? (subData ? '임차인 수정' : '신규 임차인 등록') : '정보 등록/수정';
    if (MODAL_TEMPLATES[type]) body.innerHTML = MODAL_TEMPLATES[type](subData, currentTenantId);
}

function closeModal() { document.getElementById('modal-overlay').style.display = 'none'; }

// ═══ Save & Action Functions ═══
async function doSaveTenant(isEdit) {
    const data = { tenant: {
        name: document.getElementById('ml_name').value,
        contact_phone: document.getElementById('ml_phone').value,
        personal_id: document.getElementById('ml_id').value,
        emergency_contact: document.getElementById('ml_emergency').value,
        representative_name: document.getElementById('ml_rep').value,
        address: document.getElementById('ml_addr').value,
    }};
    if (isEdit && window._modalData?.subData?.id) data.tenant.id = window._modalData.subData.id;
    const r = await fetch('/api/tenant', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data) });
    const d = await r.json();
    if (d.ok) { closeModal(); loadTenants(); loadStats(); } else alert('저장실패: ' + (d.error || ''));
}

async function saveTenant(id) {
    const data = { tenant: { id, name: document.getElementById('ft_name').value, contact_phone: document.getElementById('ft_phone').value, personal_id: document.getElementById('ft_id2').value, emergency_contact: document.getElementById('ft_emergency').value, representative_name: document.getElementById('ft_rep').value, address: document.getElementById('ft_addr').value } };
    const r = await fetch('/api/tenant', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data) });
    if ((await r.json()).ok) { loadTenants(); selectTenant(id); }
}

async function doSaveContract(isEdit) {
    const data = { contract: {
        tenant_id: document.getElementById('ml_tenant').value,
        contract_type: document.getElementById('ml_type').value,
        property_sheets: document.getElementById('ml_property').value,
        deposit_won: parseInt(document.getElementById('ml_deposit').value) || 0,
        monthly_rent_won: parseInt(document.getElementById('ml_rent').value) || 0,
        contract_start: document.getElementById('ml_start').value,
        contract_end: document.getElementById('ml_end').value,
        actual_deposit_date: document.getElementById('ml_deposit_date').value,
        renewal_flag: document.getElementById('ml_renewal').value,
        penalty_rate_pct: parseFloat(document.getElementById('ml_penalty').value) || 30,
        note: document.getElementById('ml_note').value,
    }};
    if (isEdit && window._modalData?.subData?.id) data.contract.id = window._modalData.subData.id;
    const r = await fetch('/api/contract', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data) });
    if ((await r.json()).ok) { closeModal(); if (currentTenantId) selectTenant(currentTenantId); }
}

async function doSaveMaintenance(isEdit) {
    const data = { maintenance: {
        tenant_id: document.getElementById('ml_tenant').value,
        property_no: document.getElementById('ml_prop').value,
        request_type: document.getElementById('ml_maint_type').value,
        issue_date: document.getElementById('ml_mdate').value,
        resolved_at: document.getElementById('ml_rdate').value,
        repair_cost: parseInt(document.getElementById('ml_mcost').value) || 0,
        status: document.getElementById('ml_mstatus').value,
        detail: document.getElementById('ml_mdetail').value,
    }};
    if (isEdit && window._modalData?.subData?.id) data.maintenance.id = window._modalData.subData.id;
    const r = await fetch('/api/maintenance', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data) });
    if ((await r.json()).ok) { closeModal(); if (currentTenantId) selectTenant(currentTenantId); }
}

async function doSaveArrears(isEdit) {
    const data = { arrears: {
        tenant_id: document.getElementById('ml_ar_tenant').value,
        contract_id: document.getElementById('ml_ar_contract').value,
        due_date: document.getElementById('ml_ar_due').value,
        actual_date: document.getElementById('ml_ar_actual').value,
        amount: parseInt(document.getElementById('ml_ar_amount').value) || 0,
        days_late: parseInt(document.getElementById('ml_ar_late').value) || 0,
        penalty_won: parseInt(document.getElementById('ml_ar_penalty').value) || 0,
        note: document.getElementById('ml_ar_note').value,
    }};
    if (isEdit && window._modalData?.subData?.id) data.arrears.id = window._modalData.subData.id;
    const r = await fetch('/api/arrears', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data) });
    if ((await r.json()).ok) { closeModal(); if (currentTenantId) selectTenant(currentTenantId); }
}

async function deleteTenant(id) {
    if (!confirm('임차인을 삭제하시겠습니까?')) return;
    const r = await fetch('/api/tenant/' + encodeURIComponent(id), { method: 'DELETE' });
    if ((await r.json()).ok) { currentTenantId = null; document.getElementById('mainPanel').innerHTML = '<div class="es"><div class="icon">👆</div><div>임차인을 선택하세요</div></div>'; loadTenants(); loadStats(); }
}