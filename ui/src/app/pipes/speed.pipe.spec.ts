import { SpeedPipe } from './speed.pipe';

describe('SpeedPipe', () => {
  it('returns empty string for non-positive speed values', () => {
    const pipe = new SpeedPipe();
    expect(pipe.transform(0)).toBe('');
    expect(pipe.transform(-1)).toBe('');
  });

  it('formats bytes per second values', () => {
    const pipe = new SpeedPipe();
    expect(pipe.transform(1024)).toBe('1 KB/s');
    expect(pipe.transform(1536)).toBe('1.5 KB/s');
  });

  it('formats MB/s and GB/s', () => {
    const pipe = new SpeedPipe();
    expect(pipe.transform(1024 * 1024)).toBe('1 MB/s');
    expect(pipe.transform(1024 * 1024 * 1024)).toBe('1 GB/s');
  });
});
