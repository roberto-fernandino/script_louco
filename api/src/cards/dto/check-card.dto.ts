import { IsNotEmpty, IsString, Matches } from 'class-validator';
export class CheckCardDto {
  @IsString() @IsNotEmpty() @Matches(/^\d{12,19}$/, { message: 'number deve conter entre 12 e 19 dígitos' }) number!: string;
}
