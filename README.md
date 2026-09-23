# Transactions Query Monorepo

Monorepo com uma API FastAPI e uma UI React para consultar as tabelas PostgreSQL do schema `importacao_transacoes`.

## Executar tudo localmente

```bash
# API
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edite DATABASE_URL no .env

# UI, em outro terminal
npm install
npm run dev

# API, se necessário
uvicorn app.main:app --reload
```

UI: `http://localhost:5173`.
Documentação da API: `http://localhost:8000/docs`.

## API NestJS/TypeORM

O backend NestJS fica em `api/`, enquanto o frontend existente continua em `apps/web/`.

```bash
cd api
npm install
npm run migration:run
npm run start:dev
```

A rota `POST /cards/check` recebe `{ "number": "..." }` e marca o campo `check` como `true`. A API tem os módulos `CardsModule` e `CustomerModule`, entidades em `entities/`, interfaces em `interfaces/` e repositórios TypeORM em `repositorys/`.

## Rotas

- `GET /health`
- `GET /customers` — filtros `record_id`, `email`, `document_number`, `search`, `limit`, `offset`
- `GET /customers/{record_id}`
- `GET /cards` — filtros `customer_id`, `record_id`, `brand`, `limit`, `offset`
- `GET /tables` — lista todas as tabelas do schema configurado
- `GET /tables/{table}/columns` — lista as colunas de qualquer tabela
- `GET /tables/{table}/rows` — consulta qualquer tabela com `search`, `order_by`, `descending`, `limit` e `offset`
- `PATCH /cards/{record_id}/check` — altera o campo `check` do cartão
- `POST /fraud/search` — consulta sequencialmente cartões ainda não verificados (`check != true`) e para no primeiro score acima do limite; depois consulta também o BIN do cartão

As rotas genéricas usam `importacao_transacoes` por padrão. Para outro schema permitido pelo usuário do banco, use o parâmetro `schema`.

## Consulta de fraude

Configure no `.env` as credenciais do `querybuscas` (`QUERYBUSCAS_USERNAME` e `QUERYBUSCAS_PASSWORD`). O backend segue o mesmo fluxo do `check_bins.py`: login, cookie de sessão, nonce/sig novo e consulta do score/BIN. O score usa a escala de `0` a `1000`; o botão **Buscar fraude** consulta uma transação por vez até encontrar uma acima do limite e permite marcar o cartão como verificado. As credenciais devem permanecer somente no backend e nunca ser commitadas.

Para testar a integração diretamente:

```bash
source .venv/bin/activate
export QUERYBUSCAS_USERNAME='seu_usuario'
export QUERYBUSCAS_PASSWORD='sua_senha'
python3 test_querybuscas_integration.py 09386765632 --card 5502091234567890
```

Os campos de cartão são dados sensíveis. Restrinja o acesso à API e, em produção, considere mascarar `number` e remover `cvv` das respostas.
