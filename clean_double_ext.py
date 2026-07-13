#!/usr/bin/env python3
"""에이전트가 폭파시킨 .pd.pdf 및 .pdf.pdf 이중 확장자 긴급 수습 스크립트"""
import os
import sqlite3

DL_DIR = "/Users/uglywolf/.hermes/scripts/gdrive_downloads"
DB_PATH = "/Users/uglywolf/.hermes/scripts/ocr_database.db"

print("=== 🚨 이중 확장자 대참사 긴급 복구 파이프라인 시작 ===\n")

disk_ok = 0
db_ok   = 0

# 1. 디스크 파일명 정상화 (.pd.pdf 또는 .pdf.pdf ➔ .pdf)
if os.path.exists(DL_DIR):
    for f in sorted(os.listdir(DL_DIR)):
        fp = os.path.join(DL_DIR, f)
        if not os.path.isfile(fp):
            continue
            
        lower_f = f.lower()
        new_name = None
        
        # 잘못 복원되어 생긴 .pd.pdf 처리
        if lower_f.endswith('.pd.pdf'):
            new_name = f[:-7] + '.pdf'  # 뒤의 '.pd.pdf'(7자) 자르고 '.pdf' 붙임
        # 원래 꼬여있던 .pdf.pdf 처리
        elif lower_f.endswith('.pdf.pdf'):
            new_name = f[:-4]  # 뒤의 '.pdf'(4자) 자름
        