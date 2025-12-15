import { Pipe, PipeTransform } from "@angular/core";

@Pipe({
    name: 'fileSize',
})
export class FileSizePipe implements PipeTransform {
  transform(value: number): string {
      if (isNaN(value) || value === 0) return '0 Bytes';

      const units = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
      const unitIndex = Math.floor(Math.log(value) / Math.log(1000)); // Use 1000 for common units

      const unitValue = value / Math.pow(1000, unitIndex);
      return `${unitValue.toFixed(2)} ${units[unitIndex]}`;
  }
}