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
      return `${value}s`;
    }
    if (value < 3600) {
      return `${Math.floor(value/60)}m ${value%60}s`;
    }
    const hours = Math.floor(value/3600)
    const minutes = value % 3600
    return `${hours}h ${Math.floor(minutes/60)}m ${minutes%60}s`;
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
