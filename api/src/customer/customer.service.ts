import { Inject, Injectable, NotFoundException } from '@nestjs/common';
import { ICustomerRepository } from '../interfaces/customer.repository.interface';
import { CUSTOMER_REPOSITORY } from './customer.constants';
@Injectable()
export class CustomerService {
  constructor(@Inject(CUSTOMER_REPOSITORY) private readonly repository: ICustomerRepository) {}
  async findById(recordId: string) {
    const customer = await this.repository.findById(recordId);
    if (!customer) throw new NotFoundException('Cliente não encontrado');
    return customer;
  }
}
