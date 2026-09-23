import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Customer } from '../entities/customer.entity';
import { CustomerRepository } from '../repositorys/customer.repository';
import { CUSTOMER_REPOSITORY } from './customer.constants';
import { CustomerController } from './customer.controller';
import { CustomerService } from './customer.service';
@Module({ imports: [TypeOrmModule.forFeature([Customer])], controllers: [CustomerController], providers: [CustomerService, CustomerRepository, { provide: CUSTOMER_REPOSITORY, useExisting: CustomerRepository }] })
export class CustomerModule {}
