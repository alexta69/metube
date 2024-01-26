import { Pipe, PipeTransform } from '@angular/core';

@Pipe({
  name: 'eta'
})
export class EtaPipe implements PipeTransform {
  transform(value: number, ...args: any[]): any {
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

@Pipe({
  name: 'speed'
})
export class SpeedPipe implements PipeTransform {
  transform(value: number, ...args: any[]): any {
    if (value === null) {
      return null;
    }
    const k = 1024;
    const dm = 2;
    const sizes = ['B/s', 'KB/s', 'MB/s', 'GB/s', 'TB/s', 'PB/s', 'EB/s', 'ZB/s', 'YB/s'];
    const i = Math.floor(Math.log(value) / Math.log(k));
    return parseFloat((value / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  }
}

@Pipe({
  name: 'encodeURIComponent'
})
export class EncodeURIComponent implements PipeTransform {
  transform(value: string, ...args: any[]): any {
    return encodeURIComponent(value);
  }
}

@Pipe({ 
  name: 'fileSize' 
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