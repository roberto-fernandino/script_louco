export interface ICardRepository { markCheckedByNumber(number: string): Promise<number>; }
