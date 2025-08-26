// Core batch import logic tests - isolated from Angular dependencies
describe('Batch Import Core Logic', () => {
  
  // URL validation function (extracted from our component logic)
  function validateUrls(urlText: string) {
    const urls = urlText
      .split(/\r?\n/)
      .map(url => url.trim())
      .filter(url => url.length > 0);
    
    const parsedUrlCount = urls.length;
    
    if (urls.length === 0) {
      return { valid: [], invalid: [], duplicates: [], parsedUrlCount };
    }

    // Basic URL validation regex
    const urlRegex = /^https?:\/\/.+/i;
    const valid: string[] = [];
    const invalid: string[] = [];
    const seen = new Set<string>();
    const duplicates: string[] = [];

    urls.forEach(url => {
      if (seen.has(url)) {
        if (!duplicates.includes(url)) {
          duplicates.push(url);
        }
        return;
      }
      seen.add(url);

      if (urlRegex.test(url)) {
        valid.push(url);
      } else {
        invalid.push(url);
      }
    });

    return { valid, invalid, duplicates, parsedUrlCount };
  }

  describe('URL Validation Logic', () => {
    it('should handle empty input', () => {
      const result = validateUrls('');
      expect(result.parsedUrlCount).toBe(0);
      expect(result.valid).toEqual([]);
      expect(result.invalid).toEqual([]);
      expect(result.duplicates).toEqual([]);
    });

    it('should validate single valid URL', () => {
      const result = validateUrls('https://youtube.com/watch?v=test');
      expect(result.parsedUrlCount).toBe(1);
      expect(result.valid).toEqual(['https://youtube.com/watch?v=test']);
      expect(result.invalid).toEqual([]);
      expect(result.duplicates).toEqual([]);
    });

    it('should detect invalid URLs', () => {
      const result = validateUrls('invalid-url\nnot-a-url');
      expect(result.parsedUrlCount).toBe(2);
      expect(result.valid).toEqual([]);
      expect(result.invalid).toEqual(['invalid-url', 'not-a-url']);
      expect(result.duplicates).toEqual([]);
    });

    it('should detect duplicate URLs', () => {
      const urls = [
        'https://youtube.com/watch?v=test',
        'https://youtube.com/watch?v=test',
        'https://youtube.com/watch?v=unique'
      ].join('\n');
      
      const result = validateUrls(urls);
      expect(result.parsedUrlCount).toBe(3);
      expect(result.valid).toEqual([
        'https://youtube.com/watch?v=test',
        'https://youtube.com/watch?v=unique'
      ]);
      expect(result.invalid).toEqual([]);
      expect(result.duplicates).toEqual(['https://youtube.com/watch?v=test']);
    });

    it('should handle mixed valid, invalid, and duplicate URLs', () => {
      const urls = [
        'https://youtube.com/watch?v=test1',
        'https://youtube.com/watch?v=test1', // duplicate
        'invalid-url',
        'https://youtu.be/test2',
        'not-a-url'
      ].join('\n');
      
      const result = validateUrls(urls);
      expect(result.parsedUrlCount).toBe(5);
      expect(result.valid).toEqual([
        'https://youtube.com/watch?v=test1',
        'https://youtu.be/test2'
      ]);
      expect(result.invalid).toEqual(['invalid-url', 'not-a-url']);
      expect(result.duplicates).toEqual(['https://youtube.com/watch?v=test1']);
    });

    it('should handle whitespace and empty lines', () => {
      const urls = '  https://youtube.com/test  \n\n  \nhttps://youtu.be/test2\n\n';
      const result = validateUrls(urls);
      
      expect(result.parsedUrlCount).toBe(2);
      expect(result.valid).toEqual([
        'https://youtube.com/test',
        'https://youtu.be/test2'
      ]);
    });

    it('should accept various valid URL formats', () => {
      const validUrls = [
        'https://youtube.com/watch?v=test',
        'http://youtube.com/watch?v=test',
        'https://youtu.be/test',
        'https://www.youtube.com/playlist?list=test',
        'https://github.com/user/repo',
        'https://example.com/path/to/resource'
      ];
      
      validUrls.forEach(url => {
        const result = validateUrls(url);
        expect(result.valid).toContain(url, `${url} should be valid`);
        expect(result.invalid).not.toContain(url, `${url} should not be invalid`);
      });
    });

    it('should reject invalid URL formats', () => {
      const invalidUrls = [
        'youtube.com/watch?v=test', // missing protocol
        'ftp://youtube.com/test', // wrong protocol
        'not-a-url',
        'just-text',
        'www.example.com' // missing protocol
      ];
      
      invalidUrls.forEach(url => {
        const result = validateUrls(url);
        expect(result.invalid).toContain(url, `${url} should be invalid`);
        expect(result.valid).not.toContain(url, `${url} should not be valid`);
      });
    });

    it('should handle performance with large number of URLs', () => {
      const urls = Array.from({ length: 1000 }, (_, i) => `https://youtube.com/watch?v=test${i}`);
      const urlText = urls.join('\n');
      
      const startTime = performance.now();
      const result = validateUrls(urlText);
      const endTime = performance.now();
      
      expect(endTime - startTime).toBeLessThan(100); // Should be fast
      expect(result.valid.length).toBe(1000);
      expect(result.parsedUrlCount).toBe(1000);
    });
  });

  describe('Real-world URL Testing', () => {
    it('should validate actual YouTube URLs', () => {
      const urls = [
        'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        'https://youtu.be/jNQXAC9IVRw',
        'https://youtube.com/playlist?list=PLFgquLnL59alCl_2TQvOiD5Vgm1hCaGSI'
      ].join('\n');
      
      const result = validateUrls(urls);
      expect(result.valid.length).toBe(3);
      expect(result.invalid.length).toBe(0);
    });

    it('should handle mixed real URLs with invalid ones', () => {
      const urls = [
        'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        'invalid-youtube-url',
        'https://github.com/alexta69/metube',
        'just-plain-text',
        'https://youtu.be/jNQXAC9IVRw'
      ].join('\n');
      
      const result = validateUrls(urls);
      expect(result.valid.length).toBe(3);
      expect(result.invalid.length).toBe(2);
      expect(result.invalid).toEqual(['invalid-youtube-url', 'just-plain-text']);
    });
  });
});