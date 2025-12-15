import { Pipe, PipeTransform } from "@angular/core";
import { BehaviorSubject, throttleTime } from "rxjs";

@Pipe({
    name: 'speed',
    pure: false // Make the pipe impure so it can handle async updates
})
export class SpeedPipe implements PipeTransform {
  private speedSubject = new BehaviorSubject<number>(0);
  private formattedSpeed = '';

  constructor() {
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

  transform(value: number): string {
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