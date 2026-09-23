import { Column, Entity, JoinColumn, ManyToOne, PrimaryColumn } from 'typeorm';
import { Customer } from './customer.entity';

@Entity({ schema: 'importacao_transacoes', name: 'card' })
export class Card {
  @PrimaryColumn({ name: 'record_id', type: 'bigint' }) recordId!: string;
  @Column({ name: 'customer_id', type: 'bigint' }) customerId!: string;
  @Column({ type: 'text', nullable: true }) cvv!: string | null;
  @Column({ type: 'text', nullable: true }) brand!: string | null;
  @Column({ name: 'number', type: 'text', nullable: true }) number!: string | null;
  @Column({ name: 'holderName', type: 'text', nullable: true }) holderName!: string | null;
  @Column({ type: 'text', nullable: true }) installments!: string | null;
  @Column({ name: 'expirationYear', type: 'text', nullable: true }) expirationYear!: string | null;
  @Column({ name: 'expirationMonth', type: 'text', nullable: true }) expirationMonth!: string | null;
  @Column({ name: 'check', type: 'boolean', default: false }) check!: boolean;
  @ManyToOne(() => Customer, (customer) => customer.cards, { onDelete: 'RESTRICT' })
  @JoinColumn({ name: 'customer_id', referencedColumnName: 'recordId' }) customer!: Customer;
}
