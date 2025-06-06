import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, interval } from 'rxjs';
import { map } from 'rxjs/operators';

@Injectable({
  providedIn: 'root'
})
export class SpeedService {
  private speedBuffer = new BehaviorSubject<number[]>([]);
  private readonly BUFFER_SIZE = 10; // Keep last 10 measurements (1 second at 100ms intervals)

  // Observable that emits the mean speed every second
  public meanSpeed$: Observable<number>;

  constructor() {
    // Calculate mean speed every second
    this.meanSpeed$ = interval(1000).pipe(
      map(() => {
        const speeds = this.speedBuffer.value;
        if (speeds.length === 0) return 0;
        return speeds.reduce((sum, speed) => sum + speed, 0) / speeds.length;
      })
    );
  }

  // Add a new speed measurement
  public addSpeedMeasurement(speed: number) {
    const currentBuffer = this.speedBuffer.value;
    const newBuffer = [...currentBuffer, speed].slice(-this.BUFFER_SIZE);
    this.speedBuffer.next(newBuffer);
  }

  // Get the current mean speed
  public getCurrentMeanSpeed(): number {
    const speeds = this.speedBuffer.value;
    if (speeds.length === 0) return 0;
    return speeds.reduce((sum, speed) => sum + speed, 0) / speeds.length;
  }
} 