import '@testing-library/jest-dom';

// jsdom 24's Blob/File implementation omits `.text()`, which every target
// browser has supported since 2019-2020 -- polyfill it for tests only so
// component code can use the real File API without a jsdom-specific shim.
if (typeof Blob !== 'undefined' && !Blob.prototype.text) {
  Blob.prototype.text = function (this: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error);
      reader.readAsText(this);
    });
  };
}
