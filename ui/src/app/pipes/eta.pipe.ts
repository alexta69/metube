import { Pipe, PipeTransform } from "@angular/core";

@Pipe({
    name: 'eta',
})
export class EtaPipe implements PipeTransform {
  transform(value: number): string | null {
    if (value === null) {
      return null;
    }
    if (value < 60) {
      return `${Math.round(value)}s`;
    }
    if (value < 3600) {
      return `${Math.floor(value/60)}m ${Math.round(value%60)}s`;
    }
    const hours = Math.floor(value/3600)
    const minutes = value % 3600
    return `${hours}h ${Math.floor(minutes/60)}m ${Math.round(minutes%60)}s`;
  }
}