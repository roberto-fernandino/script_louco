import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Card } from '../entities/card.entity';
import { CardRepository } from '../repositorys/card.repository';
import { CARD_REPOSITORY } from './cards.constants';
import { CardsController } from './cards.controller';
import { CardsService } from './cards.service';
@Module({ imports: [TypeOrmModule.forFeature([Card])], controllers: [CardsController], providers: [CardsService, CardRepository, { provide: CARD_REPOSITORY, useExisting: CardRepository }] })
export class CardsModule {}
