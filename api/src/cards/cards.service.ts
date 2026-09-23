import { Inject, Injectable, NotFoundException } from '@nestjs/common';
import { CARD_REPOSITORY } from './cards.constants';
import { ICardRepository } from '../interfaces/card.repository.interface';
@Injectable()
export class CardsService {
  constructor(@Inject(CARD_REPOSITORY) private readonly repository: ICardRepository) {}
  async check(number: string): Promise<{ updated: number }> {
    const updated = await this.repository.markCheckedByNumber(number);
    if (updated === 0) throw new NotFoundException('Cartão não encontrado');
    return { updated };
  }
}
