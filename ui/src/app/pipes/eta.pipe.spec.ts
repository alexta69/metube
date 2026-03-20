import { EtaPipe } from './eta.pipe';

describe('EtaPipe', () => {
  it('returns null for null input', () => {
    const pipe = new EtaPipe();
    expect(pipe.transform(null as unknown as number)).toBeNull();
  });

  it('formats seconds under one minute', () => {
    const pipe = new EtaPipe();
    expect(pipe.transform(0)).toBe('0s');
    expect(pipe.transform(59)).toBe('59s');
  });

  it('formats minutes and seconds', () => {
    const pipe = new EtaPipe();
    expect(pipe.transform(60)).toBe('1m 0s');
    expect(pipe.transform(90)).toBe('1m 30s');
  });

  it('formats hours', () => {
    const pipe = new EtaPipe();
    expect(pipe.transform(3600)).toBe('1h 0m 0s');
    expect(pipe.transform(3661)).toBe('1h 1m 1s');
  });
});
