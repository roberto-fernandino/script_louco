import { MigrationInterface, QueryRunner, Table, TableColumn, TableForeignKey, TableIndex } from 'typeorm';
const schema = 'importacao_transacoes';
export class CreateTransactionTables1710000000000 implements MigrationInterface {
  async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.createSchema(schema, true);
    if (!(await queryRunner.hasTable(`${schema}.customer`))) await queryRunner.createTable(new Table({ schema, name: 'customer', columns: [
      { name: 'record_id', type: 'bigint', isPrimary: true }, { name: 'name', type: 'text', isNullable: true }, { name: 'email', type: 'text', isNullable: true }, { name: 'phone', type: 'text', isNullable: true }, { name: 'document_type', type: 'text', isNullable: true }, { name: 'document_number', type: 'text', isNullable: true }, { name: 'address_city', type: 'text', isNullable: true }, { name: 'address_state', type: 'text', isNullable: true }, { name: 'address_street', type: 'text', isNullable: true }, { name: 'address_country', type: 'text', isNullable: true }, { name: 'address_zipCode', type: 'text', isNullable: true }, { name: 'address_complement', type: 'text', isNullable: true }, { name: 'address_neighborhood', type: 'text', isNullable: true }, { name: 'address_streetNumber', type: 'text', isNullable: true }
    ] }), true);
    if (!(await queryRunner.hasTable(`${schema}.card`))) {
      await queryRunner.createTable(new Table({ schema, name: 'card', columns: [
        { name: 'record_id', type: 'bigint', isPrimary: true }, { name: 'customer_id', type: 'bigint' }, { name: 'cvv', type: 'text', isNullable: true }, { name: 'brand', type: 'text', isNullable: true }, { name: 'number', type: 'text', isNullable: true }, { name: 'holderName', type: 'text', isNullable: true }, { name: 'installments', type: 'text', isNullable: true }, { name: 'expirationYear', type: 'text', isNullable: true }, { name: 'expirationMonth', type: 'text', isNullable: true }, { name: 'check', type: 'boolean', default: false }
      ] }), true);
      await queryRunner.createForeignKey(`${schema}.card`, new TableForeignKey({ columnNames: ['customer_id'], referencedTableName: `${schema}.customer`, referencedColumnNames: ['record_id'], onDelete: 'RESTRICT' }));
    }
    let card = await queryRunner.getTable(`${schema}.card`);
    if (card && !card.columns.some((column) => column.name === 'check')) { await queryRunner.addColumn(`${schema}.card`, new TableColumn({ name: 'check', type: 'boolean', default: false, isNullable: false })); card = await queryRunner.getTable(`${schema}.card`); }
    if (card && !card.indices.some((index) => index.name === 'card_number_idx')) await queryRunner.createIndex(`${schema}.card`, new TableIndex({ name: 'card_number_idx', columnNames: ['number'] }));
  }
  async down(queryRunner: QueryRunner): Promise<void> { await queryRunner.dropTable(`${schema}.card`, true); await queryRunner.dropTable(`${schema}.customer`, true); await queryRunner.dropSchema(schema, true); }
}
