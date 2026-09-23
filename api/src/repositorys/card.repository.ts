import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Card } from '../entities/card.entity';
import { ICardRepository } from '../interfaces/card.repository.interface';

@Injectable()
export class CardRepository implements ICardRepository {
  constructor(@InjectRepository(Card) private readonly repository: Repository<Card>) {}
  async markCheckedByNumber(number: string): Promise<number> {
    const result = await this.repository.createQueryBuilder().update(Card).set({ check: true }).where('number = :number', { number }).execute();
    return result.affected ?? 0;
  }
}
