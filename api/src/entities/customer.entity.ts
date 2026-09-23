import { Column, Entity, OneToMany, PrimaryColumn } from 'typeorm';
import { Card } from './card.entity';

@Entity({ schema: 'importacao_transacoes', name: 'customer' })
export class Customer {
  @PrimaryColumn({ name: 'record_id', type: 'bigint' }) recordId!: string;
  @Column({ type: 'text', nullable: true }) name!: string | null;
  @Column({ type: 'text', nullable: true }) email!: string | null;
  @Column({ type: 'text', nullable: true }) phone!: string | null;
  @Column({ name: 'document_type', type: 'text', nullable: true }) documentType!: string | null;
  @Column({ name: 'document_number', type: 'text', nullable: true }) documentNumber!: string | null;
  @Column({ name: 'address_city', type: 'text', nullable: true }) addressCity!: string | null;
  @Column({ name: 'address_state', type: 'text', nullable: true }) addressState!: string | null;
  @Column({ name: 'address_street', type: 'text', nullable: true }) addressStreet!: string | null;
  @Column({ name: 'address_country', type: 'text', nullable: true }) addressCountry!: string | null;
  @Column({ name: 'address_zipCode', type: 'text', nullable: true }) addressZipCode!: string | null;
  @Column({ name: 'address_complement', type: 'text', nullable: true }) addressComplement!: string | null;
  @Column({ name: 'address_neighborhood', type: 'text', nullable: true }) addressNeighborhood!: string | null;
  @Column({ name: 'address_streetNumber', type: 'text', nullable: true }) addressStreetNumber!: string | null;
  @OneToMany(() => Card, (card) => card.customer) cards!: Card[];
}
