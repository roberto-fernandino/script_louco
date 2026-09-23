import 'reflect-metadata';
import { DataSource } from 'typeorm';
import { Card } from '../entities/card.entity';
import { Customer } from '../entities/customer.entity';
export default new DataSource({
  type: 'postgres', host: process.env.PGHOST ?? '127.0.0.1', port: Number(process.env.PGPORT ?? 5433),
  username: process.env.PGUSER ?? 'importador', password: process.env.PGPASSWORD ?? 'LocalTransacoes2026',
  database: process.env.PGDATABASE ?? 'transacoes', schema: 'importacao_transacoes', entities: [Card, Customer], migrations: ['src/database/migrations/*{.ts,.js}']
});
