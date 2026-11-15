"""시세 수집·조회 서비스 진입점.

하나의 FastAPI 프로세스 안에서 두 가지 일을 한다 (docs/architecture.md 2장).
- Collector: 백그라운드 스레드로 주기마다 업비트 시세를 받아 저장 (collector.py)
- API Server: /api/v1 조회 API (api.py), 프론트 HTML, 운영용 엔드포인트 (이 파일)

운영용 엔드포인트
- GET /health  : 프로세스가 살아 있으면 항상 200 (ALB 헬스 체크용, DB를 보지 않는다)
- GET /ready   : DB 연결까지 확인, 실패하면 503
- GET /metrics : Prometheus 메트릭 (모니터링 서버만 접근, ALB로는 노출하지 않음)
"""

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match

import collector
import db
from api import ApiError, router
from metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS_TOTAL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("app")

INDEX_HTML = Path(__file__).with_name("static").joinpath("index.html").read_text(encoding="utf-8")


@asynccontextmanager
async def lifespan(app):
    # DB가 아직 안 떠 있어도 기다리지 않고 시작한다. 그동안 /ready와 조회 API는 503이다.
    db.pool.open(wait=False)
    stop = collector.start()
    yield
    stop.set()
    db.pool.close()


app = FastAPI(title="시세 수집·조회 서비스", lifespan=lifespan, docs_url=None, redoc_url=None)
app.include_router(router)


# --- 요청 메트릭 -------------------------------------------------------
def route_template(request):
    """요청이 걸리는 라우트의 템플릿 경로. 어떤 라우트에도 안 걸리면 'unmatched'."""
    for route in request.app.router.routes:
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            return route.path
    return "unmatched"


@app.middleware("http")
async def record_http_metrics(request: Request, call_next):
    path = route_template(request)
    start = time.perf_counter()
    status_code = 500  # 처리 중 예외가 밖으로 나가면 500으로 센다
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        HTTP_REQUEST_DURATION.labels(path=path).observe(time.perf_counter() - start)
        HTTP_REQUESTS_TOTAL.labels(path=path, status=str(status_code)).inc()


# --- 오류 응답 (docs/api.md 3장) ----------------------------------------
def error_response(http_status, code, message):
    return JSONResponse(
        status_code=http_status,
        content={"error": {"code": code, "message": message}},
    )


@app.exception_handler(ApiError)
async def handle_api_error(request, exc: ApiError):
    return error_response(exc.http_status, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request, exc: RequestValidationError):
    # FastAPI 기본값은 422지만, 명세대로 400 INVALID_PARAMETER로 바꾼다
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", []) if p != "query")
    return error_response(400, "INVALID_PARAMETER", f"{where}: {first.get('msg', '잘못된 값')}")


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request, exc: StarletteHTTPException):
    codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
    return error_response(exc.status_code, codes.get(exc.status_code, "HTTP_ERROR"), str(exc.detail))


@app.exception_handler(psycopg.OperationalError)
async def handle_db_unavailable(request, exc):
    # DB 연결 실패·풀 대기 시간 초과 (PoolTimeout도 OperationalError다)
    logger.warning("DB 연결 실패: %s", exc)
    return error_response(503, "DB_UNAVAILABLE", "DB에 연결할 수 없습니다")


@app.exception_handler(Exception)
async def handle_unexpected(request, exc):
    logger.exception("처리하지 못한 예외", exc_info=exc)
    return error_response(500, "INTERNAL_ERROR", "서버 내부 오류")


# --- 화면·운영용 엔드포인트 ---------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX_HTML


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    db.ping()  # 실패하면 위 핸들러가 503 DB_UNAVAILABLE로 응답한다
    return {"status": "ok", "db": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
