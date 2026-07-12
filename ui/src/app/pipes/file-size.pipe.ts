import { Pipe, PipeTransform } from "@angular/core";

@Pipe({
    name: 'fileSize',
})
export class FileSizePipe implements PipeTransform {
  transform(value: number): string {
      if (isNaN(value) || value === 0) return '0 Bytes';

      const units = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
      const k = 1024; // Matches SpeedPipe's base so file sizes and transfer speeds agree.
      const unitIndex = Math.floor(Math.log(value) / Math.log(k));

      const unitValue = value / Math.pow(k, unitIndex);
      return `${unitValue.toFixed(2)} ${units[unitIndex]}`;
  }
}