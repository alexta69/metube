import { EtaPipe } from './eta.pipe';

describe('EtaPipe', () => {
  let pipe: EtaPipe;

  beforeEach(() => {
    pipe = new EtaPipe();
  });

  it('should create an instance', () => {
    expect(pipe).toBeTruthy();
  });

  it('should return null for null input', () => {
    expect(pipe.transform(null)).toBeNull();
  });

  it('should format seconds less than 60', () => {
    expect(pipe.transform(0)).toBe('0s');
    expect(pipe.transform(30)).toBe('30s');
    expect(pipe.transform(59)).toBe('59s');
    expect(pipe.transform(59.4)).toBe('59s');
    expect(pipe.transform(59.6)).toBe('60s');
  });

  it('should format time between 60 seconds and 1 hour', () => {
    expect(pipe.transform(60)).toBe('1m 0s');
    expect(pipe.transform(90)).toBe('1m 30s');
    expect(pipe.transform(150)).toBe('2m 30s');
    expect(pipe.transform(3599)).toBe('59m 59s');
  });

  it('should format time over 1 hour', () => {
    expect(pipe.transform(3600)).toBe('1h 0m 0s');
    expect(pipe.transform(3661)).toBe('1h 1m 1s');
    expect(pipe.transform(7200)).toBe('2h 0m 0s');
    expect(pipe.transform(7323)).toBe('2h 2m 3s');
    expect(pipe.transform(36000)).toBe('10h 0m 0s');
  });

  it('should handle large time values', () => {
    expect(pipe.transform(86400)).toBe('24h 0m 0s'); // 1 day
    expect(pipe.transform(90061)).toBe('25h 1m 1s'); // 25 hours, 1 minute, 1 second
  });

  it('should round seconds appropriately', () => {
    expect(pipe.transform(59.4)).toBe('59s');
    expect(pipe.transform(59.6)).toBe('60s');
    expect(pipe.transform(3600.4)).toBe('1h 0m 0s');
    expect(pipe.transform(3600.6)).toBe('1h 0m 1s');
  });
});
