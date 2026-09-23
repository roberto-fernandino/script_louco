import { Controller, Get, Param, ParseIntPipe } from '@nestjs/common';
import { CustomerService } from './customer.service';
@Controller('customers')
export class CustomerController {
  constructor(private readonly customerService: CustomerService) {}
  @Get(':recordId') findById(@Param('recordId', ParseIntPipe) recordId: number) { return this.customerService.findById(String(recordId)); }
}
