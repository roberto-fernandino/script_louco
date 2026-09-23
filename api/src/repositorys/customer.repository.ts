import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Customer } from '../entities/customer.entity';
import { ICustomerRepository } from '../interfaces/customer.repository.interface';

@Injectable()
export class CustomerRepository implements ICustomerRepository {
  constructor(@InjectRepository(Customer) private readonly repository: Repository<Customer>) {}
  findById(recordId: string): Promise<Customer | null> { return this.repository.findOne({ where: { recordId } }); }
}
