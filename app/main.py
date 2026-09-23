import re
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .database import get_session

settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0", debug=settings.debug)
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
    search: str | None = None,
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

    if search:
        searchable = [f'"{column}"::text ILIKE :search' for column in columns]
        conditions.append(f"({' OR '.join(searchable)})")
        params["search"] = f"%{search}%"
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
