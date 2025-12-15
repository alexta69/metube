import { FileSizePipe } from './file-size.pipe';

describe('FileSizePipe', () => {
  let pipe: FileSizePipe;

  beforeEach(() => {
    pipe = new FileSizePipe();
  });

  it('should create an instance', () => {
    expect(pipe).toBeTruthy();
  });

  it('should return "0 Bytes" for zero or invalid input', () => {
    expect(pipe.transform(0)).toBe('0 Bytes');
    expect(pipe.transform(NaN)).toBe('0 Bytes');
  });

  it('should format bytes correctly', () => {
    expect(pipe.transform(500)).toBe('500.00 Bytes');
    expect(pipe.transform(999)).toBe('999.00 Bytes');
  });

  it('should format kilobytes correctly', () => {
    expect(pipe.transform(1000)).toBe('1.00 KB');
    expect(pipe.transform(1500)).toBe('1.50 KB');
    expect(pipe.transform(999999)).toBe('1000.00 KB');
  });

  it('should format megabytes correctly', () => {
    expect(pipe.transform(1000000)).toBe('1.00 MB');
    expect(pipe.transform(1500000)).toBe('1.50 MB');
    expect(pipe.transform(52428800)).toBe('52.43 MB'); // 50 MB in binary, ~52.43 MB in decimal
  });

  it('should format gigabytes correctly', () => {
    expect(pipe.transform(1000000000)).toBe('1.00 GB');
    expect(pipe.transform(1500000000)).toBe('1.50 GB');
    expect(pipe.transform(5368709120)).toBe('5.37 GB'); // 5 GB in binary, ~5.37 GB in decimal
  });

  it('should format terabytes correctly', () => {
    expect(pipe.transform(1000000000000)).toBe('1.00 TB');
    expect(pipe.transform(1500000000000)).toBe('1.50 TB');
  });

  it('should format very large sizes correctly', () => {
    expect(pipe.transform(1000000000000000)).toBe('1.00 PB'); // Petabyte
    expect(pipe.transform(1000000000000000000)).toBe('1.00 EB'); // Exabyte
  });

  it('should always show 2 decimal places', () => {
    expect(pipe.transform(1234567)).toBe('1.23 MB');
    expect(pipe.transform(1234567890)).toBe('1.23 GB');
    expect(pipe.transform(1234)).toBe('1.23 KB');
  });
});
