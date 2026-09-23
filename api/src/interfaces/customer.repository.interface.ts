import { Customer } from '../entities/customer.entity';
export interface ICustomerRepository { findById(recordId: string): Promise<Customer | null>; }
