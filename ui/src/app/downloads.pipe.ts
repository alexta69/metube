import { Pipe, PipeTransform } from '@angular/core';
import { SpeedService } from './speed.service';
import { BehaviorSubject } from 'rxjs';
import { throttleTime } from 'rxjs/operators';

@Pipe({
    name: 'eta',
    standalone: false
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
    name: 'speed',
    standalone: false,
    pure: false // Make the pipe impure so it can handle async updates
})
export class SpeedPipe implements PipeTransform {
  private speedSubject = new BehaviorSubject<number>(0);
  private formattedSpeed: string = '';

  constructor(private speedService: SpeedService) {
    // Throttle updates to once per second
    this.speedSubject.pipe(
      throttleTime(1000)
    ).subscribe(speed => {
      // If speed is invalid or 0, return empty string
      if (speed === null || speed === undefined || isNaN(speed) || speed <= 0) {
        this.formattedSpeed = '';
        return;
      }
      
      const k = 1024;
      const dm = 2;
      const sizes = ['B/s', 'KB/s', 'MB/s', 'GB/s', 'TB/s', 'PB/s', 'EB/s', 'ZB/s', 'YB/s'];
      const i = Math.floor(Math.log(speed) / Math.log(k));
      this.formattedSpeed = parseFloat((speed / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    });
  }

  transform(value: number, ...args: any[]): any {
    // If speed is invalid or 0, return empty string
    if (value === null || value === undefined || isNaN(value) || value <= 0) {
      return '';
    }
    
    // Update the speed subject
    this.speedSubject.next(value);
    
    // Return the last formatted speed
    return this.formattedSpeed;
  }
}

@Pipe({
    name: 'encodeURIComponent',
    standalone: false
})
export class EncodeURIComponent implements PipeTransform {
  transform(value: string, ...args: any[]): any {
    return encodeURIComponent(value);
  }
}

@Pipe({
    name: 'fileSize',
    standalone: false
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