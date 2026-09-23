# API NestJS

API com somente dois módulos de negócio: `CardsModule` e `CustomerModule`. Entidades ficam em `src/entities`, interfaces em `src/interfaces` e todas as implementações de persistência em `src/repositorys`.

```bash
npm install
npm run migration:run
npm run start:dev
```

Para gerar e administrar migrations:

```bash
npm run migration:generate -- src/database/migrations/NomeDaAlteracao
npm run migration:run
npm run migration:revert
```

Rotas:

```http
POST /cards/check
Content-Type: application/json

{"number":"5502095576502969"}
```

```http
GET /customers/:recordId
```
