import asyncio
import re
import time
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .backup import run_startup_backup
from .config import get_settings
from .database import get_session

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # One database backup per API start; runs in the background so startup is not delayed.
    backup_task = asyncio.create_task(run_startup_backup())
    yield
    if not backup_task.done():
        backup_task.cancel()


app = FastAPI(title=settings.app_name, version="1.0.0", debug=settings.debug, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "PATCH"],
    allow_headers=["*"],
)
Session = Annotated[AsyncSession, Depends(get_session)]
DEFAULT_SCHEMA = "importacao_transacoes"
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


class CheckUpdate(BaseModel):
    check: bool


class FraudSearchRequest(BaseModel):
    min_score: float = 800
    max_checks: int = 100
    customer_record_id: int | None = None
    customer_name: str | None = None
    customer_document: str | None = None
    card_record_id: int | None = None
    card_brand: str | None = None


def rows(result) -> list[dict]:
    return [dict(row) for row in result.mappings().all()]


def validate_identifier(value: str, label: str = "identifier") -> str:
    if not IDENTIFIER.fullmatch(value):
        raise HTTPException(status_code=400, detail=f"Invalid {label}")
    return value


async def table_columns(session: AsyncSession, table: str, schema: str = DEFAULT_SCHEMA) -> list[str]:
    result = await session.execute(
        text("""SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = :schema AND table_name = :table
                ORDER BY ordinal_position"""),
        {"schema": schema, "table": table},
    )
    columns = [row[0] for row in result.all()]
    if not columns:
        raise HTTPException(status_code=404, detail="Table not found")
    return columns


async def related_customer_data(session: AsyncSession, customer_id: int, card_record_id: int) -> dict:
    customer_result = await session.execute(
        text('SELECT * FROM importacao_transacoes.customer WHERE "record_id" = :customer_id'),
        {"customer_id": customer_id},
    )
    card_result = await session.execute(
        text('SELECT * FROM importacao_transacoes.card WHERE "record_id" = :card_record_id'),
        {"card_record_id": card_record_id},
    )
    card = dict(card_result.mappings().first() or {})
    if "number" in card:
        card["number"] = f"****{str(card['number'])[-4:]}" if card["number"] else None
    card.pop("cvv", None)
    related: dict[str, list[dict]] = {
        "customer": [dict(customer_result.mappings().first() or {})],
        "card": [card],
    }
    tables_result = await session.execute(
        text("""SELECT DISTINCT table_name
                FROM information_schema.columns
                WHERE table_schema = :schema AND column_name = 'customer_id'
                ORDER BY table_name"""),
        {"schema": DEFAULT_SCHEMA},
    )
    for (table,) in tables_result.all():
        if table == "card":
            continue
        columns = await table_columns(session, table)
        selected = ", ".join(f'"{column}"' for column in columns)
        result = await session.execute(
            text(f'''SELECT {selected} FROM "{DEFAULT_SCHEMA}"."{table}"
                    WHERE "customer_id" = :customer_id'''),
            {"customer_id": customer_id},
        )
        related[table] = rows(result)
    return related


async def fraud_scan_cursor(session: AsyncSession) -> tuple[int, int]:
    await session.execute(text("""CREATE TABLE IF NOT EXISTS importacao_transacoes.fraud_scan_progress (
        scan_name text PRIMARY KEY,
        last_card_record_id bigint NOT NULL DEFAULT 0,
        last_page bigint NOT NULL DEFAULT 0,
        updated_at timestamptz NOT NULL DEFAULT now()
    )"""))
    await session.execute(text("""INSERT INTO importacao_transacoes.fraud_scan_progress (scan_name)
        VALUES ('fraud_search') ON CONFLICT (scan_name) DO NOTHING"""))
    result = await session.execute(text("""SELECT last_card_record_id, last_page
        FROM importacao_transacoes.fraud_scan_progress WHERE scan_name = 'fraud_search'"""))
    row = result.one()
    return int(row[0]), int(row[1])


async def save_fraud_scan_cursor(session: AsyncSession, card_record_id: int, page: int) -> None:
    await session.execute(text("""UPDATE importacao_transacoes.fraud_scan_progress
        SET last_card_record_id = :card_record_id, last_page = :page, updated_at = now()
        WHERE scan_name = 'fraud_search'"""), {"card_record_id": card_record_id, "page": page})
    await session.commit()


@app.get("/tables")
async def list_tables(session: Session, schema: str = DEFAULT_SCHEMA) -> dict:
    schema = validate_identifier(schema, "schema")
    result = await session.execute(
        text("""SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = :schema AND table_type = 'BASE TABLE'
                ORDER BY table_name"""),
        {"schema": schema},
    )
    tables = [row[0] for row in result.all()]
    return {"schema": schema, "tables": tables}


@app.get("/tables/{table}/columns")
async def list_table_columns(table: str, session: Session, schema: str = DEFAULT_SCHEMA) -> dict:
    schema = validate_identifier(schema, "schema")
    table = validate_identifier(table, "table")
    return {"schema": schema, "table": table, "columns": await table_columns(session, table, schema)}


@app.get("/tables/{table}/rows")
async def query_table(
    table: str,
    session: Session,
    schema: str = DEFAULT_SCHEMA,
    filter_column: str | None = None,
    filter_value: str | None = None,
    order_by: str | None = None,
    descending: bool = False,
    limit: int = Query(default=settings.default_page_size, ge=1, le=settings.max_page_size),
    offset: int = Query(default=0, ge=0),
) -> dict:
    schema = validate_identifier(schema, "schema")
    table = validate_identifier(table, "table")
    columns = await table_columns(session, table, schema)
    selected_columns = ", ".join(f'"{column}"' for column in columns)
    params: dict[str, object] = {"limit": limit, "offset": offset}
    conditions: list[str] = []

    if filter_column and filter_value:
        filter_column = validate_identifier(filter_column, "filter_column")
        if filter_column not in columns:
            raise HTTPException(status_code=400, detail="filter_column must be a column from the selected table")
        conditions.append(f'"{filter_column}"::text ILIKE :filter_value')
        params["filter_value"] = f"%{filter_value}%"
    if order_by:
        order_by = validate_identifier(order_by, "order_by")
        if order_by not in columns:
            raise HTTPException(status_code=400, detail="order_by must be a column from the selected table")
    else:
        order_by = columns[0]
    direction = "DESC" if descending else "ASC"
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    result = await session.execute(
        text(f'''SELECT {selected_columns}
                FROM "{schema}"."{table}" {where}
                ORDER BY "{order_by}" {direction}
                LIMIT :limit OFFSET :offset'''),
        params,
    )
    return {
        "schema": schema,
        "table": table,
        "columns": columns,
        "items": rows(result),
        "limit": limit,
        "offset": offset,
    }


@app.patch("/cards/{record_id}/check")
async def update_card_check(record_id: int, payload: CheckUpdate, session: Session) -> dict:
    result = await session.execute(
        text('''UPDATE importacao_transacoes.card
                SET "check" = :check
                WHERE "record_id" = :record_id
                RETURNING "record_id", "customer_id", "check"'''),
        {"record_id": record_id, "check": payload.check},
    )
    card = result.mappings().first()
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    await session.commit()
    return dict(card)


def find_scores(value: object) -> dict[str, float]:
    scores: dict[str, float] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).upper()
            if normalized_key in {"CSB8", "CSBA", "SCORE", "FRAUD_SCORE", "RISCO", "RISK_SCORE"}:
                try:
                    scores[str(key)] = float(item)
                except (TypeError, ValueError):
                    pass
            scores.update(find_scores(item))
    elif isinstance(value, list):
        for item in value:
            scores.update(find_scores(item))
    return scores


def rate_limit_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(0.0, min(float(retry_after), 300.0))
        except ValueError:
            pass
    reset = response.headers.get("X-RateLimit-Reset")
    if reset:
        try:
            return max(0.0, min(float(reset) - time.time(), 300.0))
        except ValueError:
            pass
    return settings.querybuscas_retry_delay_seconds * (attempt + 1)


async def querybuscas_login(client: httpx.AsyncClient) -> None:
    base = settings.querybuscas_base_url.rstrip("/")
    for attempt in range(settings.querybuscas_max_retries + 1):
        response = await client.post(
            f"{base}/api/auth/login",
            json={"username": settings.querybuscas_username, "password": settings.querybuscas_password},
            headers={"Accept": "*/*", "Origin": base, "Referer": f"{base}/"},
        )
        if response.status_code != 429 or attempt >= settings.querybuscas_max_retries:
            break
        await asyncio.sleep(rate_limit_delay(response, attempt))
    data = response.json() if response.content else {}
    if response.status_code == 429:
        raise HTTPException(status_code=429, detail="querybuscas bloqueou novas tentativas de login temporariamente")
    if response.status_code == 403 and data.get("statusMessage") == "PlanExpired":
        raise HTTPException(status_code=403, detail="Plano do querybuscas expirado")
    if response.status_code != 200 or not data.get("success"):
        raise HTTPException(status_code=502, detail=f"Login no querybuscas falhou: {data.get('message') or data.get('statusMessage') or response.status_code}")


async def querybuscas_nonce(client: httpx.AsyncClient) -> tuple[str, str]:
    base = settings.querybuscas_base_url.rstrip("/")
    for attempt in range(settings.querybuscas_max_retries + 1):
        response = await client.post(
            f"{base}/api/consultas/nonce",
            headers={"Accept": "*/*", "Origin": base, "Referer": f"{base}/pages/consultas/Score"},
        )
        if response.status_code != 429 or attempt >= settings.querybuscas_max_retries:
            break
        await asyncio.sleep(rate_limit_delay(response, attempt))
    data = response.json() if response.content else {}
    if response.status_code != 200 or "nonce" not in data or "sig" not in data:
        raise HTTPException(status_code=502, detail=f"Nonce do querybuscas falhou ({response.status_code})")
    return data["nonce"], data["sig"]


async def querybuscas_score(client: httpx.AsyncClient, document: str) -> dict:
    base = settings.querybuscas_base_url.rstrip("/")
    last_response: httpx.Response | None = None
    for attempt in range(settings.querybuscas_max_retries + 1):
        nonce, signature = await querybuscas_nonce(client)
        response = await client.get(
            f"{base}/api/consultas/score/{document}",
            headers={"Accept": "*/*", "x-qb-nonce": nonce, "x-qb-sig": signature, "Referer": f"{base}/pages/consultas/Score"},
        )
        if response.status_code != 429:
            response.raise_for_status()
            return response.json() if response.content else {}
        last_response = response
        if attempt < settings.querybuscas_max_retries:
            await asyncio.sleep(rate_limit_delay(response, attempt))
    retry_after = last_response.headers.get("Retry-After") if last_response else None
    raise HTTPException(status_code=429, detail=f"querybuscas limitou a consulta de score; tente novamente depois{f' de {retry_after} segundos' if retry_after else ''}")


async def querybuscas_bin(client: httpx.AsyncClient, bin_code: str) -> dict:
    nonce, signature = await querybuscas_nonce(client)
    base = settings.querybuscas_base_url.rstrip("/")
    response = await client.get(
        f"{base}/api/consultas/bin/{bin_code}",
        headers={"Accept": "*/*", "x-qb-nonce": nonce, "x-qb-sig": signature, "Referer": f"{base}/pages/consultas/Bin"},
    )
    data = response.json() if response.content else {}
    if response.status_code == 403 and data.get("requireCaptcha"):
        raise HTTPException(status_code=403, detail="querybuscas solicitou captcha para a consulta de BIN")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Consulta de BIN falhou ({response.status_code})")
    data["BIN"] = data.get("BIN") or bin_code
    return data


@app.post("/fraud/search")
async def search_fraud(payload: FraudSearchRequest, session: Session) -> dict:
    if payload.min_score < 0 or payload.min_score > 1000:
        raise HTTPException(status_code=400, detail="min_score must be between 0 and 1000")
    if payload.max_checks < 1 or payload.max_checks > 1000:
        raise HTTPException(status_code=400, detail="max_checks must be between 1 and 1000")
    if not settings.querybuscas_username or not settings.querybuscas_password:
        raise HTTPException(status_code=503, detail="QUERYBUSCAS_USERNAME e QUERYBUSCAS_PASSWORD não configurados")

    conditions = [
        'c."document_number" IS NOT NULL',
        'TRIM(c."document_number") <> \'\'',
        'card."number" IS NOT NULL',
        'TRIM(card."number") <> \'\'',
        'card."check" IS NOT TRUE',
    ]
    last_card_record_id, last_page = await fraud_scan_cursor(session)
    params: dict[str, object] = {"limit": payload.max_checks, "last_card_record_id": last_card_record_id}
    conditions.append('card."record_id" > :last_card_record_id')
    if payload.customer_record_id is not None:
        conditions.append('c."record_id" = :customer_record_id')
        params["customer_record_id"] = payload.customer_record_id
    if payload.customer_name:
        conditions.append('c."name" ILIKE :customer_name')
        params["customer_name"] = f"%{payload.customer_name}%"
    if payload.customer_document:
        conditions.append('c."document_number" ILIKE :customer_document')
        params["customer_document"] = f"%{payload.customer_document}%"
    if payload.card_record_id is not None:
        conditions.append('card."record_id" = :card_record_id')
        params["card_record_id"] = payload.card_record_id
    if payload.card_brand:
        conditions.append('card."brand" ILIKE :card_brand')
        params["card_brand"] = f"%{payload.card_brand}%"
    result = await session.execute(
                text(f'''SELECT c."record_id", c."name", c."email", c."document_number",
                               card."customer_id" AS linked_customer_id,
                               card."record_id" AS card_record_id, card."number" AS card_number,
                               card."brand" AS local_card_brand, card."check" AS card_check
                FROM importacao_transacoes.customer c
                INNER JOIN importacao_transacoes.card card ON card."customer_id" = c."record_id"
                WHERE {' AND '.join(conditions)}
                ORDER BY card."record_id" LIMIT :limit'''),
        params,
    )
    candidates = [dict(row) for row in result.mappings().all()]
    if not candidates and last_card_record_id > 0:
        last_card_record_id = 0
        last_page = 0
        params["last_card_record_id"] = 0
        result = await session.execute(
            text(f'''SELECT c."record_id", c."name", c."email", c."document_number",
                           card."customer_id" AS linked_customer_id,
                           card."record_id" AS card_record_id, card."number" AS card_number,
                           card."brand" AS local_card_brand, card."check" AS card_check
                    FROM importacao_transacoes.customer c
                    INNER JOIN importacao_transacoes.card card ON card."customer_id" = c."record_id"
                    WHERE {' AND '.join(conditions)}
                    ORDER BY card."record_id" LIMIT :limit'''),
            params,
        )
        candidates = [dict(row) for row in result.mappings().all()]
    checked = 0
    async with httpx.AsyncClient(timeout=settings.querybuscas_timeout_seconds) as client:
        await querybuscas_login(client)
        for candidate in candidates:
            last_page += 1
            await save_fraud_scan_cursor(session, int(candidate["card_record_id"]), last_page)
            document = re.sub(r"\D", "", str(candidate["document_number"]))
            if not document:
                continue
            try:
                data = await querybuscas_score(client, document)
                scores = find_scores(data)
                score = max(scores.values()) if scores else None
                checked += 1
                if score is not None and score >= payload.min_score:
                    bin_data = None
                    card_number = re.sub(r"\D", "", str(candidate.get("card_number") or ""))
                    if len(card_number) >= 6:
                        bin_data = await querybuscas_bin(client, card_number[:6])
                    return {
                        "found": True,
                        "score": score,
                        "scores": scores,
                        "checked": checked,
                        "customer": {key: value for key, value in candidate.items() if key not in {"card_number"}},
                        "querybuscas_score": data,
                        "bin": bin_data,
                        "related_data": await related_customer_data(session, int(candidate["record_id"]), int(candidate["card_record_id"])),
                    }
            except (httpx.HTTPError, ValueError) as error:
                raise HTTPException(status_code=502, detail=f"querybuscas request failed: {error}") from error
    return {"found": False, "score": None, "checked": checked, "customer": None}


@app.get("/health")
async def health(session: Session) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/customers")
async def list_customers(
    session: Session,
    record_id: int | None = None,
    email: str | None = None,
    document_number: str | None = None,
    search: str | None = None,
    limit: int = Query(default=settings.default_page_size, ge=1, le=settings.max_page_size),
    offset: int = Query(default=0, ge=0),
) -> dict:
    conditions = []
    params = {"limit": limit, "offset": offset}
    if record_id is not None:
        conditions.append('"record_id" = :record_id')
        params["record_id"] = record_id
    if email:
        conditions.append('"email" ILIKE :email')
        params["email"] = f"%{email}%"
    if document_number:
        conditions.append('"document_number" = :document_number')
        params["document_number"] = document_number
    if search:
        conditions.append('("name" ILIKE :search OR "email" ILIKE :search OR "phone" ILIKE :search)')
        params["search"] = f"%{search}%"
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    result = await session.execute(
        text(f'''SELECT "record_id", "name", "email", "phone", "document_type",
                       "document_number", "address_city", "address_state", "address_street",
                       "address_country", "address_zipCode", "address_complement",
                       "address_neighborhood", "address_streetNumber"
                FROM importacao_transacoes.customer {where}
                ORDER BY "record_id" LIMIT :limit OFFSET :offset'''),
        params,
    )
    return {"items": rows(result), "limit": limit, "offset": offset}


@app.get("/customers/{record_id}")
async def get_customer(record_id: int, session: Session) -> dict | None:
    result = await session.execute(
        text('SELECT * FROM importacao_transacoes.customer WHERE "record_id" = :record_id'),
        {"record_id": record_id},
    )
    customer = result.mappings().first()
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return dict(customer)


@app.get("/cards")
async def list_cards(
    session: Session,
    customer_id: int | None = None,
    record_id: int | None = None,
    brand: str | None = None,
    limit: int = Query(default=settings.default_page_size, ge=1, le=settings.max_page_size),
    offset: int = Query(default=0, ge=0),
) -> dict:
    conditions = []
    params = {"limit": limit, "offset": offset}
    for column, value in (("customer_id", customer_id), ("record_id", record_id)):
        if value is not None:
            conditions.append(f'"{column}" = :{column}')
            params[column] = value
    if brand:
        conditions.append('"brand" ILIKE :brand')
        params["brand"] = f"%{brand}%"
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    result = await session.execute(
        text(f'''SELECT "record_id", "customer_id", "cvv", "brand", "number",
                       "holderName", "installments", "expirationYear", "expirationMonth", "check"
                FROM importacao_transacoes.card {where}
                ORDER BY "record_id" LIMIT :limit OFFSET :offset'''),
        params,
    )
    return {"items": rows(result), "limit": limit, "offset": offset}
