import { FileSizePipe } from './file-size.pipe';

describe('FileSizePipe', () => {
  it('returns 0 Bytes for zero or NaN', () => {
    const pipe = new FileSizePipe();
    expect(pipe.transform(0)).toBe('0 Bytes');
    expect(pipe.transform(Number.NaN)).toBe('0 Bytes');
  });

  it('formats bytes and larger units', () => {
    const pipe = new FileSizePipe();
    expect(pipe.transform(500)).toContain('Bytes');
    expect(pipe.transform(1000)).toContain('KB');
    expect(pipe.transform(1000 * 1000)).toContain('MB');
    expect(pipe.transform(1000 ** 3)).toContain('GB');
  });

  it('handles boundaries between units', () => {
    const pipe = new FileSizePipe();
    expect(pipe.transform(999)).toContain('Bytes');
    expect(pipe.transform(1000)).toContain('KB');
    expect(pipe.transform(1001)).toContain('KB');
  });
});
