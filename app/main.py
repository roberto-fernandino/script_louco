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

from .config import get_settings
from .database import get_session, run_startup_migrations

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await run_startup_migrations()
    yield


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
        card["number"] = card["number"] if card["number"] else None
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
        value = filter_value.strip()
        if filter_column == "id" or filter_column.endswith("_id"):
            conditions.append(f'"{filter_column}"::text = :filter_value')
            params["filter_value"] = value
        else:
            conditions.append(f'"{filter_column}"::text ILIKE :filter_value')
            params["filter_value"] = f"%{value}%"
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


def snoop_scores(data: dict) -> dict[str, float]:
    results = data.get("body", {}).get("resultados", [])
    if isinstance(results, dict):
        results = [results]
    scores: dict[str, float] = {}
    for result in results if isinstance(results, list) else []:
        if not isinstance(result, dict):
            continue
        for key in ("score_csb8", "score_csba"):
            try:
                if result.get(key) is not None:
                    scores[key.upper()] = float(result[key])
            except (TypeError, ValueError):
                continue
    return scores


def snoop_score_results(data: dict) -> dict[str, dict]:
    results = data.get("body", {}).get("resultados", [])
    if isinstance(results, dict):
        results = [results]
    parsed: dict[str, dict] = {}
    for result in results if isinstance(results, list) else []:
        if not isinstance(result, dict):
            continue
        cpf = re.sub(r"\D", "", str(result.get("cpf") or ""))
        if cpf:
            parsed[cpf] = result
    return parsed


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
    return settings.snoop_retry_delay_seconds * (attempt + 1)


_snoop_rate_lock = asyncio.Lock()
_snoop_next_request_at = 0.0


async def snoop_throttle() -> None:
    global _snoop_next_request_at
    if settings.snoop_rate_limit_per_second <= 0:
        return
    interval = 1.0 / settings.snoop_rate_limit_per_second
    async with _snoop_rate_lock:
        now = time.monotonic()
        wait_for = max(0.0, _snoop_next_request_at - now)
        _snoop_next_request_at = max(now, _snoop_next_request_at) + interval
    if wait_for:
        await asyncio.sleep(wait_for)


async def snoop_request(client: httpx.AsyncClient, method: str, path: str, **kwargs) -> dict:
    if not settings.snoop_api_key:
        raise HTTPException(status_code=503, detail="SNOOP_API_KEY não configurada")
    headers = dict(kwargs.pop("headers", {}))
    headers["x-api-key"] = settings.snoop_api_key
    headers.setdefault("Accept", "application/json")
    for attempt in range(settings.snoop_max_retries + 1):
        await snoop_throttle()
        try:
            response = await client.request(
                method, f"{settings.snoop_api_base_url.rstrip('/')}{path}", headers=headers, **kwargs
            )
        except httpx.HTTPError as error:
            if attempt >= settings.snoop_max_retries:
                raise HTTPException(status_code=502, detail=f"Snoop request failed: {error}") from error
            await asyncio.sleep(settings.snoop_retry_delay_seconds * (attempt + 1))
            continue
        if response.status_code == 429 or response.status_code >= 500:
            if attempt < settings.snoop_max_retries:
                await asyncio.sleep(rate_limit_delay(response, attempt))
                continue
        break
    data = response.json() if response.content else {}
    if response.status_code != 200:
        detail = data.get("message") or data.get("error") or data.get("body") or response.reason_phrase
        status = response.status_code if response.status_code in {400, 401, 402, 403, 404, 429} else 502
        raise HTTPException(status_code=status, detail=f"Snoop API ({response.status_code}): {detail}")
    return data


async def snoop_scores_batch(client: httpx.AsyncClient, documents: list[str]) -> dict[str, dict]:
    try:
        data = await snoop_request(client, "POST", "/api/rendaescore", json={"cpfs": documents})
    except HTTPException as error:
        if error.status_code == 404:
            return {}
        raise
    return snoop_score_results(data)


async def snoop_bin(client: httpx.AsyncClient, bin_code: str) -> dict:
    try:
        data = await snoop_request(client, "GET", "/api/query/bin", params={"bin": bin_code})
    except HTTPException as error:
        if error.status_code == 404:
            return {}
        raise
    body = data.get("body", data)
    return {"BIN": body.get("bin") or bin_code, **body}


@app.post("/fraud/search")
async def search_fraud(payload: FraudSearchRequest, session: Session) -> dict:
    if payload.min_score < 0 or payload.min_score > 1000:
        raise HTTPException(status_code=400, detail="min_score must be between 0 and 1000")
    if payload.max_checks < 1 or payload.max_checks > 1000:
        raise HTTPException(status_code=400, detail="max_checks must be between 1 and 1000")
    if not settings.snoop_api_key:
        raise HTTPException(status_code=503, detail="SNOOP_API_KEY não configurada")

    conditions = [
        'c."document_number" IS NOT NULL',
        'TRIM(c."document_number") <> \'\'',
        'card."number" IS NOT NULL',
        'TRIM(card."number") <> \'\'',
    ]
    # An explicit card lookup must also be able to render its full fraud result
    # when the card was already checked; the normal scan still skips checked cards.
    if payload.card_record_id is None:
        conditions.append('card."check" IS NOT TRUE')
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
                               card."brand" AS local_card_brand, card."check" AS card_check,
                               c."score_csb8", c."score_csba", c."score_csb8_faixa", c."score_csba_faixa",
                               c."score_updated_at"
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
                           card."brand" AS local_card_brand, card."check" AS card_check,
                           c."score_csb8", c."score_csba", c."score_csb8_faixa", c."score_csba_faixa",
                           c."score_updated_at"
                    FROM importacao_transacoes.customer c
                    INNER JOIN importacao_transacoes.card card ON card."customer_id" = c."record_id"
                    WHERE {' AND '.join(conditions)}
                    ORDER BY card."record_id" LIMIT :limit'''),
            params,
        )
        candidates = [dict(row) for row in result.mappings().all()]
    checked = 0
    async with httpx.AsyncClient(timeout=settings.snoop_timeout_seconds) as client:
        documents = []
        seen_documents: set[str] = set()
        for candidate in candidates:
            document = re.sub(r"\D", "", str(candidate["document_number"]))
            if (document and candidate.get("score_updated_at") is None
                    and candidate.get("score_csb8") is None and candidate.get("score_csba") is None
                    and document not in seen_documents):
                seen_documents.add(document)
                documents.append(document)
        score_results: dict[str, dict] = {}
        for start in range(0, len(documents), 400):
            score_results.update(await snoop_scores_batch(client, documents[start:start + 400]))
        for document, result_data in score_results.items():
            score_csb8 = result_data.get("score_csb8")
            score_csba = result_data.get("score_csba")
            await session.execute(
                text('''UPDATE importacao_transacoes.customer
                        SET "score_csb8" = :score_csb8,
                            "score_csba" = :score_csba,
                            "score_csb8_faixa" = :score_csb8_faixa,
                            "score_csba_faixa" = :score_csba_faixa,
                            "score_updated_at" = now()
                        WHERE regexp_replace("document_number", '\\D', '', 'g') = :document'''),
                {"score_csb8": score_csb8, "score_csba": score_csba,
                 "score_csb8_faixa": result_data.get("score_csb8_faixa"),
                 "score_csba_faixa": result_data.get("score_csba_faixa"), "document": document},
            )
        if documents:
            await session.execute(
                text('''UPDATE importacao_transacoes.customer
                        SET "score_updated_at" = now()
                        WHERE regexp_replace("document_number", '\\D', '', 'g') = ANY(CAST(:documents AS text[]))
                          AND "score_updated_at" IS NULL'''),
                {"documents": documents},
            )
        if documents:
            await session.commit()
        for candidate in candidates:
            last_page += 1
            await save_fraud_scan_cursor(session, int(candidate["card_record_id"]), last_page)
            document = re.sub(r"\D", "", str(candidate["document_number"]))
            if not document:
                continue
            try:
                data = score_results.get(document, {
                    "score_csb8": candidate.get("score_csb8"),
                    "score_csba": candidate.get("score_csba"),
                    "score_csb8_faixa": candidate.get("score_csb8_faixa"),
                    "score_csba_faixa": candidate.get("score_csba_faixa"),
                })
                scores = {key.upper(): float(value) for key, value in (
                    ("score_csb8", data.get("score_csb8")), ("score_csba", data.get("score_csba"))
                ) if value is not None}
                score = max(scores.values()) if scores else None
                checked += 1
                # An explicit card filter is a detail lookup, so render the
                # fraud result even when its score is below the scan threshold
                # or Snoop returns no score value.
                if payload.card_record_id is not None or (score is not None and score >= payload.min_score):
                    bin_data = None
                    card_number = re.sub(r"\D", "", str(candidate.get("card_number") or ""))
                    if len(card_number) >= 6:
                        bin_data = await snoop_bin(client, card_number[:6])
                    related_data = await related_customer_data(
                        session, int(candidate["record_id"]), int(candidate["card_record_id"])
                    )
                    return {
                        "found": True,
                        "score": score,
                        "scores": scores,
                        "checked": checked,
                        "customer": {key: value for key, value in candidate.items() if key not in {"card_number"}},
                        "card": related_data["card"][0] if related_data["card"] else None,
                        "snoop_score": data,
                        "bin": bin_data,
                        "related_data": related_data,
                    }
            except ValueError as error:
                raise HTTPException(status_code=502, detail=f"Snoop response inválida: {error}") from error
    return {"found": False, "score": None, "checked": checked, "customer": None}


@app.get("/cards/{record_id}/details")
async def card_details(record_id: int, session: Session) -> dict:
    result = await session.execute(
        text('''SELECT c."record_id", c."name", c."email", c."document_number",
                      card."customer_id" AS linked_customer_id,
                      card."record_id" AS card_record_id,
                      card."brand" AS local_card_brand,
                      card."check" AS card_check
               FROM importacao_transacoes.customer c
               INNER JOIN importacao_transacoes.card card ON card."customer_id" = c."record_id"
               WHERE card."record_id" = :record_id'''),
        {"record_id": record_id},
    )
    candidate = dict(result.mappings().first() or {})
    if not candidate:
        raise HTTPException(status_code=404, detail="Card not found")
    related_data = await related_customer_data(session, int(candidate["record_id"]), record_id)
    return {
        "found": True,
        "score": None,
        "scores": {},
        "checked": 0,
        "customer": candidate,
        "card": related_data["card"][0] if related_data["card"] else None,
        "snoop_score": None,
        "bin": None,
        "related_data": related_data,
    }


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
