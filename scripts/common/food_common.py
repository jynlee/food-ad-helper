# -*- coding: utf-8 -*-
"""
food_common.py
식품 표시·광고 도우미 챗봇 — 공통 유틸리티
(에스테틱 챗봇 mazel_common.py 에서 PostgreSQL 부분을 빼고 파일 로그로 바꿈)

포함 함수:
- loadConfig  : .env 로드 → 설정 딕셔너리 반환
- retryGet    : GET 요청 실패 시 최대 N회 재시도 (선형 백오프)
- getOsClient : OpenSearch 클라이언트 반환
- appendLog   : 수집 이력을 logs/<kind>.jsonl 에 한 줄씩 기록
                (나중에 OpenSearch collect-log 인덱스로 옮길 때는 이 함수 안쪽만 바꾼다)
"""

# ============================================================
# 라이브러리 임포트
# ============================================================

import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from opensearchpy import OpenSearch


# ============================================================
# 상수 정의
# ============================================================

ROOT          = Path(__file__).resolve().parents[2]
LOG_DIR       = ROOT / "logs"
LOG_KINDS     = ("collect", "law_history")
FOOD_TYPE_MAP = {"general": "일반식품", "health": "건강기능식품"}
COMMON        = "공통"


# ============================================================
# 설정 로드
# ============================================================

def loadConfig():
    """
    프로젝트 루트의 .env 파일을 로드하고 설정값을 딕셔너리로 반환.
    이미 환경변수로 들어 있는 값이 있으면 그 값을 우선한다.
    """
    load_dotenv(ROOT / ".env")

    cfg = {
        # OpenSearch
        'osHost':     os.getenv("OS_HOST",     "https://localhost:9200"),
        'osUser':     os.getenv("OS_USER",     "admin"),
        'osPassword': os.getenv("OS_PASSWORD", ""),

        # Ollama
        'ollamaHost': os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
        'embedModel': os.getenv("EMBED_MODEL", "bge-m3"),
        'llmModel':   os.getenv("LLM_MODEL",   "gemma4:e4b"),

        # Redis (질문-답변 시맨틱 캐시)
        'redisHost':        os.getenv("REDIS_HOST",     "localhost"),
        'redisPort':        int(os.getenv("REDIS_PORT", 6379)),
        'redisDb':          int(os.getenv("REDIS_DB",   0)),
        'redisPassword':    os.getenv("REDIS_PASSWORD", ""),
        'qaCacheThreshold': float(os.getenv("QA_CACHE_THRESHOLD", 0.95)),
        'qaCacheTtlSec':    int(os.getenv("QA_CACHE_TTL_SEC", 60 * 60 * 24 * 7)),

        # 공공데이터 API
        'lawApiKey':     os.getenv("LAW_OC",         ""),
        'foodsafetyKey': os.getenv("FOODSAFETY_KEY", ""),
    }
    return cfg


# ============================================================
# API 재시도 유틸
# ============================================================

def retryGet(url, params, maxRetry=5, sleepSec=2):
    """
    GET 요청 실패 시 최대 maxRetry회 재시도 (선형 백오프: 2s, 4s, 6s...).
    - ConnectionError / Timeout / 429 → 재시도
    - 그 외 HTTPError (4xx/5xx)       → 즉시 raise
    """
    lastErr = None
    for attempt in range(0, maxRetry):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                waitSec = sleepSec * (attempt + 2)
                print(f"  [retry {attempt+1}/{maxRetry}] Rate limit, {waitSec}s 대기")
                time.sleep(waitSec)
                lastErr = requests.exceptions.HTTPError("429 Too Many Requests")
                continue
            resp.raise_for_status()
            return resp
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.ChunkedEncodingError) as e:
            lastErr = e
            if attempt < maxRetry - 1:
                waitSec = sleepSec * (attempt + 1)
                print(f"  [retry {attempt+1}/{maxRetry}] {type(e).__name__}, {waitSec}s 대기")
                time.sleep(waitSec)
    raise lastErr or RuntimeError("retryGet 최대 재시도 초과")


# ============================================================
# OpenSearch 클라이언트
# ============================================================

def getOsClient(cfg):
    """
    OpenSearch 클라이언트 객체 반환.
    개발 환경 데모 인증서 사용으로 SSL 검증 비활성화.
    """
    stripped = cfg['osHost'].replace("https://", "").replace("http://", "")
    useSSL   = cfg['osHost'].startswith("https")
    if ":" in stripped:
        rawHost, rawPort = stripped.rsplit(":", 1)
        rawPort = int(rawPort)
    else:
        rawHost = stripped
        rawPort = 9200

    return OpenSearch(
        hosts=[{"host": rawHost, "port": rawPort}],
        http_auth=(cfg['osUser'], cfg['osPassword']),
        use_ssl=useSSL,
        verify_certs=False,
        ssl_show_warn=False,
    )


# ============================================================
# 수집 이력 기록
# ============================================================

def appendLog(kind, record, logDir=None):
    """
    수집 이력을 logs/<kind>.jsonl 에 한 줄(JSON)로 덧붙인다.
    kind   : "collect"(수집 실행 결과) | "law_history"(조문 변경 이력)
    record : 기록할 dict. logged_at(기록 시각)은 자동으로 붙는다.
    """
    if kind not in LOG_KINDS:
        raise ValueError(f"알 수 없는 로그 종류: {kind}")
    targetDir = Path(logDir) if logDir else LOG_DIR
    targetDir.mkdir(parents=True, exist_ok=True)
    row = {"logged_at": datetime.now().isoformat(timespec="seconds")}
    row.update(record)
    with open(targetDir / f"{kind}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
