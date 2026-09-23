import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { CardsModule } from './cards/cards.module';
import { CustomerModule } from './customer/customer.module';

@Module({
  imports: [
    TypeOrmModule.forRoot({
      type: 'postgres', host: process.env.PGHOST ?? '127.0.0.1', port: Number(process.env.PGPORT ?? 5433),
      username: process.env.PGUSER ?? 'importador', password: process.env.PGPASSWORD ?? 'LocalTransacoes2026',
      database: process.env.PGDATABASE ?? 'transacoes', schema: 'importacao_transacoes', autoLoadEntities: true,
      migrations: [__dirname + '/database/migrations/*{.js,.ts}'], migrationsRun: true
    }), CardsModule, CustomerModule
  ]
})
export class AppModule {}
