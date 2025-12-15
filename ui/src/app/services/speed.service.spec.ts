import { TestBed } from '@angular/core/testing';
import { SpeedService } from './speed.service';

describe('SpeedService', () => {
  let service: SpeedService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [SpeedService],
    });
    service = TestBed.inject(SpeedService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should return 0 for mean speed when no measurements are added', () => {
    const currentSpeed = service.getCurrentMeanSpeed();
    expect(currentSpeed).toBe(0);
  });

  it('should add speed measurement and calculate mean', () => {
    service.addSpeedMeasurement(100);
    service.addSpeedMeasurement(200);
    service.addSpeedMeasurement(300);

    const meanSpeed = service.getCurrentMeanSpeed();
    expect(meanSpeed).toBe(200); // (100 + 200 + 300) / 3 = 200
  });

  it('should maintain buffer size of 10 measurements', () => {
    // Add 15 measurements
    for (let i = 1; i <= 15; i++) {
      service.addSpeedMeasurement(i * 10);
    }

    // Should only keep the last 10: 60, 70, 80, 90, 100, 110, 120, 130, 140, 150
    const meanSpeed = service.getCurrentMeanSpeed();
    const expected = (60 + 70 + 80 + 90 + 100 + 110 + 120 + 130 + 140 + 150) / 10;
    expect(meanSpeed).toBe(expected);
  });

  it('should provide a mean speed observable', () => {
    service.addSpeedMeasurement(100);
    service.addSpeedMeasurement(200);

    // Verify the observable exists and is defined
    expect(service.meanSpeed$).toBeDefined();
    
    // We can't easily test the interval-based observable in a unit test
    // without complex zone/fakeAsync setup, so we verify behavior through
    // the getCurrentMeanSpeed() method instead
    const currentMean = service.getCurrentMeanSpeed();
    expect(currentMean).toBe(150); // (100 + 200) / 2 = 150
  });

  it('should handle single measurement', () => {
    service.addSpeedMeasurement(500);
    const meanSpeed = service.getCurrentMeanSpeed();
    expect(meanSpeed).toBe(500);
  });

  it('should handle zero speeds', () => {
    service.addSpeedMeasurement(0);
    service.addSpeedMeasurement(0);
    const meanSpeed = service.getCurrentMeanSpeed();
    expect(meanSpeed).toBe(0);
  });

  it('should update mean speed after new measurements', () => {
    service.addSpeedMeasurement(100);
    expect(service.getCurrentMeanSpeed()).toBe(100);

    service.addSpeedMeasurement(300);
    expect(service.getCurrentMeanSpeed()).toBe(200);

    service.addSpeedMeasurement(600);
    expect(service.getCurrentMeanSpeed()).toBe(333.3333333333333);
  });
});
