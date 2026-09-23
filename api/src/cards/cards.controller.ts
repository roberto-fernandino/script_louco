import { Body, Controller, Post } from '@nestjs/common';
import { CardsService } from './cards.service';
import { CheckCardDto } from './dto/check-card.dto';
@Controller('cards')
export class CardsController {
  constructor(private readonly cardsService: CardsService) {}
  @Post('check') check(@Body() dto: CheckCardDto): Promise<{ updated: number }> { return this.cardsService.check(dto.number); }
}
